"""Offline checks for the isolated real-task runner."""

import json
import os
import subprocess

import pytest

from validation import checks, compare, review_case, run_case, summary


def _git(repo, *args):
    return subprocess.run(["git", *args], cwd=repo, check=True,
                          capture_output=True, text=True, encoding="utf-8").stdout.strip()


def test_checkout_and_result_categories(tmp_path, monkeypatch):
    source = tmp_path / "source"
    source.mkdir()
    _git(source, "init", "-q")
    _git(source, "config", "user.name", "Test")
    _git(source, "config", "user.email", "test@example.invalid")
    (source / ".gitignore").write_text(".env\n", encoding="utf-8")
    (source / "allowed.py").write_text("value = 1\n", encoding="utf-8")
    _git(source, "add", ".gitignore", "allowed.py")
    _git(source, "commit", "-qm", "baseline")
    baseline = _git(source, "rev-parse", "HEAD")
    (source / ".env").write_text("SECRET=must-not-be-copied\n", encoding="utf-8")
    (source / "grading.txt").write_text("not tracked\n", encoding="utf-8")
    monkeypatch.setattr(run_case, "SOURCE", source)
    monkeypatch.setattr(run_case, "BASELINE", baseline)

    checkout = tmp_path / "checkout"
    run_case.prepare_checkout(checkout)
    assert _git(checkout, "rev-parse", "HEAD") == baseline
    assert not (checkout / ".env").exists()
    assert not (checkout / "grading.txt").exists()

    (checkout / "allowed.py").write_text("value = 2\n", encoding="utf-8")
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()
    changes = run_case.collect_changes(checkout, artifacts)
    assert changes["tracked_files"] == ["allowed.py"]
    assert changes["untracked_files"] == []
    assert "allowed.py" in changes["stat"]
    assert "value = 2" in (artifacts / "changes.diff").read_text(encoding="utf-8")

    ok = {"exit_code": 0, "timed_out": False}
    assert run_case.classify(ok, ok, changes, ["allowed.py"]) == (
        "valid", "needs_review", "manual_case_checks_pending")
    assert run_case.classify(ok, ok, changes, ["allowed.py"], "automatic",
                             {"exit_code": 0, "timed_out": False,
                              "result": {"passed": True}})[1] == "passed"
    assert run_case.classify(ok, ok, changes, ["allowed.py"], "automatic",
                             {"exit_code": 1, "timed_out": False,
                              "result": {"passed": False}})[1] == "failed"
    assert run_case.classify({"exit_code": 1, "timed_out": False}, ok,
                             changes, ["allowed.py"])[0] == "invalid"
    assert run_case.classify(ok, {"exit_code": 1, "timed_out": False},
                             changes, ["allowed.py"])[1] == "failed"
    assert run_case.classify(ok, {"exit_code": 2, "timed_out": False},
                             changes, ["allowed.py"])[1] == "failed"
    (checkout / "extra.py").write_text("x = 1\n", encoding="utf-8")
    changes = run_case.collect_changes(checkout, artifacts)
    assert changes["untracked_files"] == ["extra.py"]
    assert run_case.classify(ok, ok, changes, ["allowed.py"])[1] == "failed"


def test_catalog_and_separate_summary(tmp_path):
    assert set(run_case.CASES) == set(range(1, 21))
    automatic = {i for i, case in run_case.CASES.items() if case["grading"] == "automatic"}
    manual = {i for i, case in run_case.CASES.items() if case["grading"] == "manual"}
    assert automatic == checks.AUTOMATIC_IDS
    assert len(automatic) == 14 and len(manual) == 6
    assert len({case["prompt"] for case in run_case.CASES.values()}) == 20

    records = [
        {"case": 1, "grading": "automatic", "execution_status": "valid", "task_outcome": "passed"},
        {"case": 3, "grading": "automatic", "execution_status": "valid", "task_outcome": "failed"},
        {"case": 4, "grading": "automatic", "execution_status": "invalid", "task_outcome": None},
        {"case": 2, "grading": "manual", "execution_status": "valid", "task_outcome": "needs_review"},
        {"case": 16, "grading": "manual", "execution_status": "invalid", "task_outcome": None},
    ]
    report = summary.summarize(records)
    assert report["catalog"] == {"total": 20, "automatic": 14, "manual": 6}
    assert report["automatic"]["success_rate"] == 0.5
    assert report["automatic"]["valid"] == 2
    assert report["automatic"]["invalid_runs"] == 1
    assert report["automatic"]["not_run"] == 11
    assert report["manual"]["needs_review"] == 1
    assert report["manual"]["invalid_runs"] == 1
    assert report["manual"]["not_run"] == 4
    precheck_failure = {"case": 17, "grading": "manual", "execution_status": "valid",
                        "task_outcome": "failed", "reason": "existing_tests_failed"}
    report_with_precheck = summary.summarize(records + [precheck_failure])
    assert report_with_precheck["manual"]["failed_precheck"] == 1
    assert report_with_precheck["automatic"]["success_rate"] == 0.5
    with pytest.raises(ValueError, match="multiple valid runs"):
        summary.summarize(records + [records[0]])

    path = tmp_path / "result.json"
    path.write_text(json.dumps(records[3]), encoding="utf-8")
    reviewed = review_case.record_review(path, "passed", "注释说明了分词误差，未作绝对化断言")
    assert reviewed["task_outcome"] == "passed"
    report = summary.summarize(records[:3] + [reviewed])
    assert report["automatic"]["success_rate"] == 0.5
    assert report["manual"]["passed_after_review"] == 1


def _check_subprocess(case_id, checkout, baseline, scratch):
    output = scratch / f"check-{case_id}.json"
    env = os.environ.copy()
    env.pop("OPENAI_API_KEY", None)
    env["PYTHONPATH"] = str(checkout / "src")
    proc = subprocess.run(
        [os.sys.executable, str(run_case.SOURCE / "validation" / "checks.py"),
         "--case", str(case_id), "--checkout", str(checkout),
         "--baseline", baseline, "--scratch-root", str(scratch),
         "--output", str(output)],
        cwd=checkout, env=env, capture_output=True, text=True, timeout=30,
    )
    assert proc.returncode in (0, 1), proc.stderr
    result = json.loads(output.read_text(encoding="utf-8"))
    return result["passed"]


def test_automatic_checks_reject_baseline_and_accept_reference_fixes(tmp_path):
    checkout = tmp_path / "checkout"
    run_case.prepare_checkout(checkout)
    assert all(not _check_subprocess(i, checkout, run_case.BASELINE, tmp_path)
               for i in sorted(checks.AUTOMATIC_IDS))

    read_path = checkout / "src/mindev/tools/read.py"
    baseline_read = read_path.read_text(encoding="utf-8")
    read_path.write_text(
        baseline_read + "\n\ndef read_lines(path, n):\n"
        "    try:\n"
        "        with open(path, encoding='utf-8') as file:\n"
        "            return ''.join(file.readlines()[:max(n, 0)])\n"
        "    except FileNotFoundError:\n"
        "        return 'Error: file not found'\n",
        encoding="utf-8",
    )
    assert _check_subprocess(1, checkout, run_case.BASELINE, tmp_path)
    read_path.write_text(baseline_read.replace("MAX_OUTPUT_CHARS = 20_000",
                                              "MAX_OUTPUT_CHARS = 10_000"), encoding="utf-8")
    assert _check_subprocess(3, checkout, run_case.BASELINE, tmp_path)

    edit_path = checkout / "src/mindev/tools/edit.py"
    edit_path.write_text(edit_path.read_text(encoding="utf-8").replace(
        "MAX_EDIT_CHARS = 100_000", "MAX_EDIT_CHARS = 50_000"), encoding="utf-8")
    assert _check_subprocess(4, checkout, run_case.BASELINE, tmp_path)

    permissions_path = checkout / "src/mindev/agent/permissions.py"
    permissions_path.write_text(permissions_path.read_text(encoding="utf-8").replace(
        '        if risk == "read":\n',
        '        if risk not in ("read", "write", "command"):\n'
        '            return False\n'
        '        if risk == "read":\n'), encoding="utf-8")
    assert _check_subprocess(13, checkout, run_case.BASELINE, tmp_path)

    repomap_path = checkout / "src/mindev/context/repomap.py"
    repomap_path.write_text(repomap_path.read_text(encoding="utf-8").replace(
        'SOURCE_EXTENSIONS = {".py", ".js", ".go"}',
        'SOURCE_EXTENSIONS = {".py", ".pyi", ".js", ".go"}').replace(
        '    if ext == ".py":', '    if ext in (".py", ".pyi"):'), encoding="utf-8")
    assert _check_subprocess(14, checkout, run_case.BASELINE, tmp_path)


def test_remaining_automatic_checks_accept_reference_fixes(tmp_path):
    checkout = tmp_path / "checkout"
    run_case.prepare_checkout(checkout)

    def verify(case_id, rel, modified):
        path = checkout / rel
        original = path.read_text(encoding="utf-8")
        path.write_text(modified(original), encoding="utf-8")
        try:
            assert _check_subprocess(case_id, checkout, run_case.BASELINE, tmp_path)
        finally:
            path.write_text(original, encoding="utf-8")

    verify(5, "src/mindev/sandbox/local.py",
           lambda s: s.replace("MAX_OUTPUT_CHARS = 20_000", "MAX_OUTPUT_CHARS = 10_000"))
    verify(6, "src/mindev/tools/edit.py",
           lambda s: s.replace("from .base import Tool", "from pathlib import Path\n\nfrom .base import Tool")
           .replace("        if self._snapshots:\n", "        Path(path).parent.mkdir(parents=True, exist_ok=True)\n"
                    "        if self._snapshots:\n", 1))
    verify(7, "src/mindev/tools/edit.py",
           lambda s: s.replace(
               "        if self._snapshots:\n            self._snapshots.snapshot(path)\n"
               "        updated = original.replace(old, new, 1)",
               "        if old == new:\n            return 'No-op: unchanged.'\n"
               "        if self._snapshots:\n            self._snapshots.snapshot(path)\n"
               "        updated = original.replace(old, new, 1)"))
    verify(8, "src/mindev/tools/snapshot.py",
           lambda s: s.replace("    def snapshot(self, path: str) -> None:\n",
                               "    def has_snapshot(self, path: str) -> bool:\n"
                               "        return path in self._states\n\n"
                               "    def snapshot(self, path: str) -> None:\n"))
    verify(9, "src/mindev/tools/registry.py",
           lambda s: s.replace("        self._tools: dict[str, Tool] = {tool.name: tool for tool in tools}",
                               "        names = [tool.name for tool in tools]\n"
                               "        if len(names) != len(set(names)):\n"
                               "            raise ValueError('duplicate tool name')\n"
                               "        self._tools: dict[str, Tool] = {tool.name: tool for tool in tools}"))
    verify(10, "src/mindev/agent/trace.py",
           lambda s: s.replace('            "events": len(self.events),',
                               '            "events": len(self.events),\n'
                               '            "compact_events": sum(e.kind == "compact" for e in self.events),'))
    verify(11, "src/mindev/agent/trace.py",
           lambda s: s + "\n    def clear(self) -> None:\n        self.events.clear()\n")
    verify(12, "src/mindev/agent/session.py",
           lambda s: s + "\n    def delete(self) -> None:\n"
                         "        try:\n            os.remove(self._path)\n"
                         "        except FileNotFoundError:\n            pass\n")
    verify(15, "src/mindev/tools/registry.py",
           lambda s: s + "\n    def names(self) -> list[str]:\n"
                         "        return sorted(self._tools)\n")


def test_runner_uses_current_agent_and_checks_baseline_code(tmp_path, monkeypatch):
    import dotenv

    monkeypatch.setattr(dotenv, "load_dotenv", lambda *a, **k: None)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    calls = []

    def fake_execute(command, cwd, env, stdout_path, stderr_path, timeout):
        calls.append((command, cwd, env))
        if len(calls) == 1:
            from mindev.sandbox.workspace import create_workspace

            agent_workspace = create_workspace(cwd, command[command.index("--output-dir") + 1])
            candidate = agent_workspace / "src/mindev/tools/read.py"
            candidate.write_text(candidate.read_text(encoding="utf-8") + "\n# agent edit\n",
                                 encoding="utf-8")
            usage_path = command[command.index("--usage-file") + 1]
            with open(usage_path, "w", encoding="utf-8") as file:
                json.dump({"source": "api_response_usage", "complete": True,
                           "requests": 2, "prompt_tokens": 20,
                           "completion_tokens": 3, "total_tokens": 23}, file)
        return {"exit_code": 0, "timed_out": False, "seconds": 0}

    monkeypatch.setattr(run_case, "execute", fake_execute)
    path = run_case.run_case(1, tmp_path, "test-model", 10, 10)
    result = json.loads(path.read_text(encoding="utf-8"))
    checkout = path.parent / "checkout"
    agent_workspace = path.parent / "agent-workspace"
    assert len(calls) == 3  # Agent, original tests, deterministic checker
    assert "--no-bash" in calls[0][0]
    assert calls[0][0][calls[0][0].index("--output-dir") + 1] == str(agent_workspace)
    assert calls[0][1] == checkout
    assert calls[0][2]["PYTHONPATH"].split(os.pathsep)[0] == str(run_case.SOURCE / "src")
    assert calls[0][2]["PYTHONIOENCODING"] == "utf-8"
    assert calls[1][2]["PYTHONPATH"].split(os.pathsep)[0] == str(agent_workspace / "src")
    assert calls[1][2]["PYTHONIOENCODING"] == "utf-8"
    assert calls[2][2]["PYTHONPATH"].split(os.pathsep)[0] == str(agent_workspace / "src")
    assert result["checkout"] == str(agent_workspace)
    assert result["source_checkout"] == str(checkout)
    assert result["changes"]["tracked_files"] == ["src/mindev/tools/read.py"]
    assert "# agent edit" not in (checkout / "src/mindev/tools/read.py").read_text(encoding="utf-8")
    assert result["checkout_head"] == run_case.BASELINE
    assert len(result["agent_source_sha256"]) == 64
    assert result["api_usage"]["total_tokens"] == 23
    assert result["context_estimate"]["source"] == "trace_character_count_divided_by_four"


def test_compare_rejects_model_mismatch_and_separates_actual_from_estimate():
    def record(case_id, outcome, repomap, model="fixed"):
        return {"case": case_id, "grading": "automatic", "execution_status": "valid",
                "task_outcome": outcome, "baseline": run_case.BASELINE,
                "model": model, "api_type": "openai_compatible_chat_completions",
                "api_endpoint_host": "example.invalid", "agent_source_sha256": "abc",
                "prompt": run_case.CASES[case_id]["prompt"],
                "configuration": {"repomap": repomap, "compact_threshold": 0,
                                  "no_bash": True, "stream": False},
                "api_usage": {"complete": True, "requests": 1, "prompt_tokens": 10,
                              "completion_tokens": 2, "total_tokens": 12},
                "context_estimate": {"peak_observed_context_tokens": 7,
                                     "compaction_events": 0}}

    a = {1: record(1, "failed", False), 3: record(3, "passed", False)}
    b = {1: record(1, "passed", True), 3: record(3, "passed", True)}
    report = compare.compare({"off": a, "on": b})
    assert report["variants"]["off"]["functional"]["automatic"]["success_rate"] == 0.5
    assert report["variants"]["on"]["actual_api_usage"]["total_tokens"] == 24
    assert report["variants"]["on"]["estimated_context"]["mean_observed_peak_context_tokens"] == 7
    assert report["paired_automatic_vs_first"]["on"]["improved"] == 1
    assert report["paired_actual_api_usage"]["automatic_cases"]["coverage"] == "2/2"
    assert report["paired_actual_api_usage"]["automatic_cases"]["variants"]["on"]["total_tokens"] == 24
    b[1]["configuration"] = a[1]["configuration"]
    with pytest.raises(ValueError, match="mixes"):
        compare.compare({"off": a, "on": b})
    b[1]["configuration"] = {"repomap": True, "compact_threshold": 0,
                              "no_bash": True, "stream": False}
    b[3]["api_usage"] = None
    assert compare.compare({"off": a, "on": b})["variants"]["on"]["actual_api_usage"]["total_tokens"] is None
    assert compare.compare({"off": a, "on": b})["paired_actual_api_usage"]["automatic_cases"]["coverage"] == "1/2"
    b[3]["api_usage"] = a[3]["api_usage"]
    b[3]["execution_status"] = "invalid"
    b[3]["task_outcome"] = None
    assert compare.compare({"off": a, "on": b})["variants"]["on"]["actual_api_usage"]["total_tokens"] is None
    b[3]["execution_status"] = "valid"
    b[3]["task_outcome"] = "passed"
    b[3]["model"] = "different"
    with pytest.raises(ValueError, match="mismatch"):
        compare.compare({"off": a, "on": b})
    b[3]["model"] = "fixed"
    a[3]["model"] = "different"
    with pytest.raises(ValueError, match="Reference runs"):
        compare.compare({"off": a, "on": b})
