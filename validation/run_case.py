"""Run one fixed real-task case in an independent checkout.

The checkout and all artifacts live outside the source tree by default. This
runner records evidence; a passing test suite is not a semantic task verdict.
"""

import argparse
import hashlib
import json
import os
import shutil
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
        "title": "read_lines 前 N 行",
        "difficulty": "medium",
        "grading": "automatic",
        "prompt": "在 src/mindev/tools/read.py 里加一个 read_lines(path, n) 函数，返回前 n 行。",
        "allowed": ["src/mindev/tools/read.py"],
        "tests": ["tests/test_tools.py"],
    },
    2: {
        "title": "估算注释准确性",
        "difficulty": "easy",
        "grading": "manual",
        "prompt": "把 src/mindev/context/repomap.py 里 estimate_tokens 的注释改得更准确。",
        "allowed": ["src/mindev/context/repomap.py"],
        "tests": ["tests/test_repomap.py", "tests/test_repomap_multilang.py"],
    },
    3: {
        "title": "读取输出上限",
        "difficulty": "easy",
        "grading": "automatic",
        "prompt": "把 src/mindev/tools/read.py 的 MAX_OUTPUT_CHARS 从 20000 改成 10000，其他逻辑保持不变。",
        "allowed": ["src/mindev/tools/read.py"],
        "tests": ["tests/test_tools.py"],
    },
    4: {
        "title": "编辑长度上限",
        "difficulty": "easy",
        "grading": "automatic",
        "prompt": "把 src/mindev/tools/edit.py 的 MAX_EDIT_CHARS 从 100000 改为 50000，其他源码保持不变。",
        "allowed": ["src/mindev/tools/edit.py"],
        "tests": ["tests/test_edit.py"],
    },
    5: {
        "title": "本地命令输出上限",
        "difficulty": "easy",
        "grading": "automatic",
        "prompt": "把 src/mindev/sandbox/local.py 的 MAX_OUTPUT_CHARS 从 20000 改为 10000，其他源码保持不变。",
        "allowed": ["src/mindev/sandbox/local.py"],
        "tests": ["tests/test_sandbox.py"],
    },
    6: {
        "title": "写文件时创建父目录",
        "difficulty": "medium",
        "grading": "automatic",
        "prompt": "修改 src/mindev/tools/edit.py：WriteFileTool 写入嵌套路径时自动创建缺失的父目录，仍保持原有覆盖文件行为。",
        "allowed": ["src/mindev/tools/edit.py"],
        "tests": ["tests/test_edit.py"],
    },
    7: {
        "title": "编辑无变化时跳过快照",
        "difficulty": "medium",
        "grading": "automatic",
        "prompt": "修改 src/mindev/tools/edit.py：EditFileTool 在 old_string 与 new_string 完全相同时返回可识别的 no-op，不写文件、不创建快照；其他编辑行为不变。",
        "allowed": ["src/mindev/tools/edit.py"],
        "tests": ["tests/test_edit.py"],
    },
    8: {
        "title": "快照存在性查询",
        "difficulty": "medium",
        "grading": "automatic",
        "prompt": "在 src/mindev/tools/snapshot.py 的 SnapshotStore 增加 has_snapshot(path) 方法：未快照返回 False，快照后返回 True，restore 后返回 False。",
        "allowed": ["src/mindev/tools/snapshot.py"],
        "tests": ["tests/test_edit.py"],
    },
    9: {
        "title": "拒绝重复工具名",
        "difficulty": "medium",
        "grading": "automatic",
        "prompt": "修改 src/mindev/tools/registry.py：ToolRegistry 构造时如果两个工具的 name 相同，抛出 ValueError，而不是静默覆盖；正常工具注册保持可用。",
        "allowed": ["src/mindev/tools/registry.py"],
        "tests": ["tests/test_tools.py"],
    },
    10: {
        "title": "追踪压缩次数",
        "difficulty": "easy",
        "grading": "automatic",
        "prompt": "修改 src/mindev/agent/trace.py：TraceRecorder.summarize() 返回值增加 compact_events，表示 kind 为 compact 的事件数量，已有统计字段不变。",
        "allowed": ["src/mindev/agent/trace.py"],
        "tests": ["tests/test_trace.py"],
    },
    11: {
        "title": "清空内存追踪事件",
        "difficulty": "medium",
        "grading": "automatic",
        "prompt": "在 src/mindev/agent/trace.py 为 TraceRecorder 增加 clear()：只清空内存中的 events，保留已有 JSONL 文件；清空后仍可继续 record。",
        "allowed": ["src/mindev/agent/trace.py"],
        "tests": ["tests/test_trace.py"],
    },
    12: {
        "title": "删除会话文件",
        "difficulty": "medium",
        "grading": "automatic",
        "prompt": "在 src/mindev/agent/session.py 为 SessionStore 增加 delete()：删除当前会话文件；文件不存在时也不报错。",
        "allowed": ["src/mindev/agent/session.py"],
        "tests": ["tests/test_session.py"],
    },
    13: {
        "title": "未知风险默认拒绝",
        "difficulty": "hard",
        "grading": "automatic",
        "prompt": "修改 src/mindev/agent/permissions.py：PermissionPolicy.allow 对未知 risk 值一律返回 False；read、write、command 的现有权限行为保持不变。",
        "allowed": ["src/mindev/agent/permissions.py"],
        "tests": ["tests/test_permissions.py"],
    },
    14: {
        "title": "RepoMap 支持 pyi",
        "difficulty": "hard",
        "grading": "automatic",
        "prompt": "修改 src/mindev/context/repomap.py：RepoMap 把 .pyi 文件纳入源码列表，并像 .py 一样提取顶层函数和类符号。",
        "allowed": ["src/mindev/context/repomap.py"],
        "tests": ["tests/test_repomap.py", "tests/test_repomap_multilang.py"],
    },
    15: {
        "title": "列出已注册工具名",
        "difficulty": "medium",
        "grading": "automatic",
        "prompt": "在 src/mindev/tools/registry.py 为 ToolRegistry 增加 names() 方法，返回按字母序排列的已注册工具名列表，不改变 schemas() 顺序。",
        "allowed": ["src/mindev/tools/registry.py"],
        "tests": ["tests/test_tools.py"],
    },
    16: {
        "title": "README 评测口径说明",
        "difficulty": "medium",
        "grading": "manual",
        "prompt": "更新 README.md：向读者解释内置 3 题 eval 与真实仓库任务评测的区别，以及自动判定题和人工审阅题的成功率应分别报告。不要编造尚未测得的通过率。",
        "allowed": ["README.md"],
        "tests": ["tests/test_cli.py"],
    },
    17: {
        "title": "设计文档与实现对齐",
        "difficulty": "hard",
        "grading": "manual",
        "prompt": "只修改 DESIGN.md，修正其中与当前仓库实现不一致的文件编辑和沙箱描述，并说明默认 local 命令执行的实际边界。",
        "allowed": ["DESIGN.md"],
        "tests": ["tests/test_cli.py"],
    },
    18: {
        "title": "CLI 帮助文字",
        "difficulty": "medium",
        "grading": "manual",
        "prompt": "只修改 src/mindev/cli.py，改善 --trace、--plan、--yes 的帮助文字，让新用户清楚副作用和输出位置；选项行为保持不变。",
        "allowed": ["src/mindev/cli.py"],
        "tests": ["tests/test_cli.py"],
    },
    19: {
        "title": "Agent 循环重构",
        "difficulty": "hard",
        "grading": "manual",
        "prompt": "只修改 src/mindev/agent/loop.py，将 run 中工具执行与结果回灌的逻辑提取为易读的私有方法；保持权限、trace、observer 和退出行为不变。",
        "allowed": ["src/mindev/agent/loop.py"],
        "tests": ["tests/test_loop.py", "tests/test_permissions.py", "tests/test_trace.py"],
    },
    20: {
        "title": "Provider 错误提示",
        "difficulty": "hard",
        "grading": "manual",
        "prompt": "只修改 src/mindev/llm/openai.py，让 Chat Completions 请求失败时给出可操作的错误信息，但不泄露 API key；正常响应和工具调用行为保持不变。",
        "allowed": ["src/mindev/llm/openai.py"],
        "tests": ["tests/test_openai.py", "tests/test_stream.py"],
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


def context_estimate(trace: Path) -> dict:
    """Report character/4 context snapshots, never API-billed tokens."""
    values: list[int] = []
    reductions: list[int] = []
    if trace.exists():
        for line in trace.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(event.get("tokens"), int):
                values.append(event["tokens"])
            before = event.get("tokens_before")
            after = event.get("tokens")
            if event.get("kind") == "compact" and isinstance(before, int) and isinstance(after, int):
                values.append(before)
                reductions.append(before - after)
    return {
        "source": "trace_character_count_divided_by_four",
        "peak_observed_context_tokens": max(values) if values else None,
        "compaction_events": len(reductions),
        "compaction_reduction_tokens": sum(reductions) if reductions else None,
    }


def agent_source_digest() -> str:
    """Fingerprint the Agent code, which is separate from the task checkout."""
    root = SOURCE / "src" / "mindev"
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*.py")):
        digest.update(path.relative_to(root).as_posix().encode("utf-8"))
        digest.update(path.read_bytes())
    return digest.hexdigest()


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


def classify(agent: dict, tests: dict, changes: dict, allowed: list[str],
             grading: str = "manual", automatic: dict | None = None) -> tuple[str, str | None, str]:
    if agent["timed_out"] or agent["exit_code"] != 0:
        return "invalid", None, "agent_timeout_or_nonzero_exit"
    if tests["timed_out"] or tests["exit_code"] not in (0, 1, 2):
        return "invalid", None, "test_environment_error"
    if tests["exit_code"] in (1, 2):
        return "valid", "failed", "existing_tests_failed"
    unexpected = (set(changes["tracked_files"]) - set(allowed)) | set(changes["untracked_files"])
    if changes["env_created"] or unexpected:
        return "valid", "failed", "files_outside_allowed_set"
    if not changes["tracked_files"]:
        return "valid", "failed", "no_source_change"
    if grading == "automatic":
        if automatic is None or automatic.get("timed_out") or automatic.get("exit_code") not in (0, 1):
            return "invalid", None, "checker_environment_error"
        passed = automatic.get("result", {}).get("passed")
        if not isinstance(passed, bool) or (automatic["exit_code"] == 0) != passed:
            return "invalid", None, "checker_result_mismatch"
        if not passed:
            return "valid", "failed", "automatic_checks_failed"
        return "valid", "passed", "automatic_checks_passed"
    return "valid", "needs_review", "manual_case_checks_pending"


def run_case(case_id: int, output_root: Path, model_override: str | None,
             timeout: int, test_timeout: int, prepare_only: bool = False,
             repomap: bool = True, compact_threshold: int = 20000) -> Path:
    case = CASES[case_id]
    run_dir = output_root.resolve() / (
        f"{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}-case{case_id}-{uuid.uuid4().hex[:8]}"
    )
    run_dir.mkdir(parents=True)
    checkout = run_dir / "checkout"
    result = {
        "schema_version": 1,
        "case": case_id,
        "title": case["title"],
        "difficulty": case["difficulty"],
        "grading": case["grading"],
        "baseline": BASELINE,
        "prompt": case["prompt"],
        "allowed_files": case["allowed"],
        "checkout": str(checkout),
        "execution_status": "invalid",
        "task_outcome": None,
        "reason": "setup_incomplete",
        "configuration": {"repomap": repomap, "compact_threshold": compact_threshold,
                          "no_bash": True, "stream": False},
        "api_usage": None,
        "api_usage_note": "No API usage artifact recorded yet.",
        "context_estimate": None,
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
        result["agent_source_sha256"] = agent_source_digest()

        agent_env = os.environ.copy()
        agent_env["PYTHONPATH"] = str(SOURCE / "src") + os.pathsep + agent_env.get("PYTHONPATH", "")
        # Redirected stdout otherwise inherits the Windows GBK code page and
        # can fail after a successful Agent turn when the model prints Unicode.
        agent_env["PYTHONIOENCODING"] = "utf-8"
        trace = run_dir / "trace.jsonl"
        usage_file = run_dir / "api_usage.json"
        agent_workspace = run_dir / "agent-workspace"
        agent_cmd = [sys.executable, "-m", "mindev.cli", "run", "--yes",
                     "--no-bash", "--output-dir", str(agent_workspace),
                     "--model", model, "--trace", str(trace),
                     "--usage-file", str(usage_file),
                     "--compact-threshold", str(compact_threshold)]
        if not repomap:
            agent_cmd.append("--no-repomap")
        for allowed_file in case["allowed"]:
            agent_cmd.extend(["--allowed-file", allowed_file])
        agent_cmd.append(case["prompt"])
        result["agent_command"] = ["<python>", *agent_cmd[1:]]
        result["agent"] = execute(agent_cmd, checkout, agent_env,
                                  run_dir / "agent.stdout.log", run_dir / "agent.stderr.log", timeout)
        result["tool_calls"] = count_tool_calls(trace)
        result["trace_file"] = "trace.jsonl"
        result["context_estimate"] = context_estimate(trace)
        if usage_file.exists():
            result["api_usage"] = json.loads(usage_file.read_text(encoding="utf-8"))
            result["api_usage_file"] = "api_usage.json"
            result["api_usage_note"] = (
                "All recorded API responses include usage."
                if result["api_usage"].get("complete") else
                "Some API responses omitted usage; token totals are unknown."
            )
        else:
            result["api_usage_note"] = "API usage artifact missing; token totals are unknown."

        if not agent_workspace.is_dir():
            raise RuntimeError("Agent did not create its isolated workspace")
        # Add independent Git metadata only after the Agent has finished, so
        # grading can compare with BASELINE without exposing it to the Agent.
        shutil.copytree(checkout / ".git", agent_workspace / ".git")
        result["source_checkout"] = str(checkout)
        result["checkout"] = str(agent_workspace)

        test_cmd = [sys.executable, "-m", "pytest", *case["tests"], "-q"]
        result["test_command"] = ["<python>", *test_cmd[1:]]
        test_env = os.environ.copy()
        test_env["PYTHONPATH"] = str(agent_workspace / "src") + os.pathsep + test_env.get("PYTHONPATH", "")
        test_env["PYTHONIOENCODING"] = "utf-8"
        test_env.pop("OPENAI_API_KEY", None)
        result["tests"] = execute(test_cmd, agent_workspace, test_env,
                                  run_dir / "tests.stdout.log", run_dir / "tests.stderr.log", test_timeout)
        result["changes"] = collect_changes(agent_workspace, run_dir)
        automatic = None
        if case["grading"] == "automatic":
            checks_file = run_dir / "automatic_checks.json"
            checker_cmd = [sys.executable, str(SOURCE / "validation" / "checks.py"),
                           "--case", str(case_id), "--checkout", str(agent_workspace),
                           "--baseline", BASELINE, "--scratch-root", str(run_dir),
                           "--output", str(checks_file)]
            automatic = execute(checker_cmd, agent_workspace, test_env,
                                run_dir / "checker.stdout.log", run_dir / "checker.stderr.log", test_timeout)
            if checks_file.exists():
                automatic["result"] = json.loads(checks_file.read_text(encoding="utf-8"))
            result["automatic_checks"] = automatic
        status, outcome, reason = classify(result["agent"], result["tests"],
                                           result["changes"], case["allowed"],
                                           case["grading"], automatic)
        result.update(execution_status=status, task_outcome=outcome, reason=reason)
    except (OSError, subprocess.CalledProcessError, RuntimeError,
            AssertionError, json.JSONDecodeError) as exc:
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
    parser.add_argument("--no-repomap", action="store_true", help="Disable RepoMap in this run")
    parser.add_argument("--compact-threshold", type=int, default=20000,
                        help="Context estimate threshold; 0 disables compaction")
    args = parser.parse_args()
    if args.timeout <= 0 or args.test_timeout <= 0 or args.compact_threshold < 0:
        parser.error("timeouts must be positive and compact threshold nonnegative")
    path = run_case(args.case, args.output_root, args.model,
                    args.timeout, args.test_timeout, args.prepare_only,
                    not args.no_repomap, args.compact_threshold)
    result = json.loads(path.read_text(encoding="utf-8"))
    print(f"{result['execution_status']}/{result['task_outcome']}: {result['reason']}\n{path}")
    return 0 if result["execution_status"] == "prepared" or result["task_outcome"] in (
        "passed", "needs_review") else 1


if __name__ == "__main__":
    raise SystemExit(main())
