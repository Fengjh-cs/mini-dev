"""Run one fixed real-task case in an independent checkout.

The checkout and all artifacts live outside the source tree by default. This
runner records evidence; a passing test suite is not a semantic task verdict.
"""

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit


BASELINE = "2671d40db5342f230f22f6cad66745639c97f7bc"
SOURCE = Path(__file__).resolve().parents[1]
CASES = {
    1: {
        "prompt": "在 src/mindev/tools/read.py 里加一个 read_lines(path, n) 函数，返回前 n 行。",
        "allowed": ["src/mindev/tools/read.py"],
        "tests": ["tests/test_tools.py"],
    },
    2: {
        "prompt": "把 src/mindev/context/repomap.py 里 estimate_tokens 的注释改得更准确。",
        "allowed": ["src/mindev/context/repomap.py"],
        "tests": ["tests/test_repomap.py", "tests/test_repomap_multilang.py"],
    },
    3: {
        "prompt": "把 src/mindev/tools/read.py 的 MAX_OUTPUT_CHARS 从 20000 改成 10000，其他逻辑保持不变。",
        "allowed": ["src/mindev/tools/read.py"],
        "tests": ["tests/test_tools.py"],
    },
}


def git(*args: str, cwd: Path = SOURCE) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args], cwd=cwd, text=True, encoding="utf-8",
        errors="replace", capture_output=True, check=True,
    )


def prepare_checkout(destination: Path) -> None:
    git("clone", "--quiet", "--no-hardlinks", "--no-checkout", str(SOURCE), str(destination))
    git("checkout", "--quiet", "--detach", BASELINE, cwd=destination)
    git("remote", "remove", "origin", cwd=destination)
    assert git("rev-parse", "HEAD", cwd=destination).stdout.strip() == BASELINE
    if (destination / ".env").exists():
        raise RuntimeError("Refusing to run: checkout contains .env")


def collect_changes(checkout: Path, run_dir: Path) -> dict:
    # The stat command is deliberately identical to the documented review command.
    stat = git("diff", "--stat", BASELINE, "--", ".", cwd=checkout).stdout
    tracked = git("diff", "--name-only", "-z", BASELINE, "--", ".", cwd=checkout).stdout
    untracked = git("ls-files", "--others", "--exclude-standard", "-z", cwd=checkout).stdout
    patch = git("diff", "--binary", BASELINE, "--", ".", cwd=checkout).stdout
    (run_dir / "changes.diff").write_text(patch, encoding="utf-8")
    return {
        "stat_command": f"git diff --stat {BASELINE} -- .",
        "stat": stat,
        "tracked_files": sorted(p for p in tracked.split("\0") if p),
        "untracked_files": sorted(p for p in untracked.split("\0") if p),
        "patch_file": "changes.diff",
        "env_created": (checkout / ".env").exists(),
    }


def count_tool_calls(trace: Path) -> int:
    if not trace.exists():
        return 0
    count = 0
    for line in trace.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            count += json.loads(line).get("kind") == "tool_call"
        except json.JSONDecodeError:
            continue
    return count


def execute(command: list[str], cwd: Path, env: dict[str, str],
            stdout_path: Path, stderr_path: Path, timeout: int) -> dict:
    started = time.monotonic()
    with stdout_path.open("w", encoding="utf-8") as stdout, \
            stderr_path.open("w", encoding="utf-8") as stderr:
        try:
            completed = subprocess.run(
                command, cwd=cwd, env=env, stdout=stdout, stderr=stderr,
                timeout=timeout, check=False,
            )
            return {"exit_code": completed.returncode, "timed_out": False,
                    "seconds": round(time.monotonic() - started, 3)}
        except subprocess.TimeoutExpired:
            return {"exit_code": None, "timed_out": True,
                    "seconds": round(time.monotonic() - started, 3)}


def classify(agent: dict, tests: dict, changes: dict, allowed: list[str]) -> tuple[str, str | None, str]:
    if agent["timed_out"] or agent["exit_code"] != 0:
        return "invalid", None, "agent_timeout_or_nonzero_exit"
    if tests["timed_out"] or tests["exit_code"] not in (0, 1):
        return "invalid", None, "test_environment_error"
    if tests["exit_code"] == 1:
        return "valid", "failed", "existing_tests_failed"
    unexpected = (set(changes["tracked_files"]) - set(allowed)) | set(changes["untracked_files"])
    if changes["env_created"] or unexpected:
        return "valid", "failed", "files_outside_allowed_set"
    if not changes["tracked_files"]:
        return "valid", "failed", "no_source_change"
    return "valid", "needs_review", "manual_case_checks_pending"


def run_case(case_id: int, output_root: Path, model_override: str | None,
             timeout: int, test_timeout: int, prepare_only: bool = False) -> Path:
    case = CASES[case_id]
    run_dir = output_root.resolve() / (
        f"{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}-case{case_id}-{uuid.uuid4().hex[:8]}"
    )
    run_dir.mkdir(parents=True)
    checkout = run_dir / "checkout"
    result = {
        "schema_version": 1,
        "case": case_id,
        "baseline": BASELINE,
        "prompt": case["prompt"],
        "allowed_files": case["allowed"],
        "checkout": str(checkout),
        "execution_status": "invalid",
        "task_outcome": None,
        "reason": "setup_incomplete",
        "api_usage": None,
        "api_usage_note": "Provider does not expose response usage; trace token estimates are not API usage.",
    }
    try:
        prepare_checkout(checkout)
        result["checkout_head"] = git("rev-parse", "HEAD", cwd=checkout).stdout.strip()
        if prepare_only:
            result.update(execution_status="prepared", reason="prepare_only")
            return _save_result(run_dir, result)

        from dotenv import load_dotenv

        load_dotenv(SOURCE / ".env", override=False)
        if not os.getenv("OPENAI_API_KEY"):
            raise RuntimeError("OPENAI_API_KEY is not configured")
        model = model_override or os.getenv("MINIDEV_MODEL") or "gpt-5-mini"
        endpoint = os.getenv("OPENAI_BASE_URL") or "https://api.openai.com"
        result["model"] = model
        result["api_type"] = "openai_compatible_chat_completions"
        result["api_endpoint_host"] = urlsplit(endpoint).hostname

        env = os.environ.copy()
        env["PYTHONPATH"] = str(checkout / "src") + os.pathsep + env.get("PYTHONPATH", "")
        trace = run_dir / "trace.jsonl"
        agent_cmd = [sys.executable, "-m", "mindev.cli", "run", "--yes",
                     "--model", model, "--trace", str(trace), case["prompt"]]
        result["agent_command"] = ["<python>", *agent_cmd[1:]]
        result["agent"] = execute(agent_cmd, checkout, env,
                                  run_dir / "agent.stdout.log", run_dir / "agent.stderr.log", timeout)
        result["tool_calls"] = count_tool_calls(trace)
        result["trace_file"] = "trace.jsonl"

        test_cmd = [sys.executable, "-m", "pytest", *case["tests"], "-q"]
        result["test_command"] = ["<python>", *test_cmd[1:]]
        result["tests"] = execute(test_cmd, checkout, env,
                                  run_dir / "tests.stdout.log", run_dir / "tests.stderr.log", test_timeout)
        result["changes"] = collect_changes(checkout, run_dir)
        status, outcome, reason = classify(result["agent"], result["tests"],
                                           result["changes"], case["allowed"])
        result.update(execution_status=status, task_outcome=outcome, reason=reason)
    except (OSError, subprocess.CalledProcessError, RuntimeError, AssertionError) as exc:
        result["reason"] = "setup_or_collection_error"
        result["error_type"] = type(exc).__name__
    return _save_result(run_dir, result)


def _save_result(run_dir: Path, result: dict) -> Path:
    path = run_dir / "result.json"
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", type=int, choices=sorted(CASES), required=True)
    parser.add_argument("--output-root", type=Path,
                        default=Path(tempfile.gettempdir()) / "mindev-validation")
    parser.add_argument("--model", help="Override MINIDEV_MODEL")
    parser.add_argument("--timeout", type=int, default=300, help="Agent timeout in seconds")
    parser.add_argument("--test-timeout", type=int, default=120, help="Pytest timeout in seconds")
    parser.add_argument("--prepare-only", action="store_true", help="Create checkout without API calls")
    args = parser.parse_args()
    if args.timeout <= 0 or args.test_timeout <= 0:
        parser.error("timeouts must be positive")
    path = run_case(args.case, args.output_root, args.model,
                    args.timeout, args.test_timeout, args.prepare_only)
    result = json.loads(path.read_text(encoding="utf-8"))
    print(f"{result['execution_status']}: {result['reason']}\n{path}")
    return 0 if result["execution_status"] in ("prepared", "valid") else 1


if __name__ == "__main__":
    raise SystemExit(main())
