"""Automatic edit -> verify -> repair behavior, with optional Docker coverage."""

import os
import shutil
import subprocess

import pytest

from mindev.agent.loop import AgentLoop
from mindev.agent.trace import TraceRecorder
from mindev.agent.verify import EditVerifier, FileScopeCheck
from mindev.llm.base import LLMProvider, ToolCall, Turn
from mindev.sandbox.docker import CommandResult, DockerSandbox
from mindev.sandbox.workspace import create_workspace
from mindev.tools.access import WorkspacePathPolicy
from mindev.tools.edit import DeleteFileTool, EditFileTool, WriteFileTool
from mindev.tools.registry import ToolRegistry
from mindev.tools.snapshot import SnapshotStore


class ScriptedProvider(LLMProvider):
    def __init__(self, turns):
        self.turns = iter(turns)
        self.results = []

    def add_user(self, content):
        pass

    def send(self, tools):
        return next(self.turns)

    def add_tool_result(self, call_id, output):
        self.results.append((call_id, output))


class FakeSandbox:
    def __init__(self, check):
        self.check = check
        self.calls = []

    def run_result(self, command, timeout=60):
        self.calls.append((command, timeout))
        return self.check()


def test_hard_write_scope_blocks_extra_edit_and_returns_error_to_agent(tmp_path):
    (tmp_path / "allowed.py").write_text("old", encoding="utf-8")
    tests = tmp_path / "tests"
    tests.mkdir()
    (tests / "test_tools.py").write_text("original", encoding="utf-8")
    access = WorkspacePathPolicy(tmp_path, allowed_writes=["allowed.py"])
    provider = ScriptedProvider([
        Turn("", [ToolCall("extra", "edit_file", {
            "path": "tests/test_tools.py", "old_string": "original", "new_string": "extra",
        })]),
        Turn("", [ToolCall("source", "edit_file", {
            "path": "allowed.py", "old_string": "old", "new_string": "new",
        })]),
        Turn("done", []),
    ])
    recorder = TraceRecorder()
    loop = AgentLoop(
        provider, ToolRegistry([EditFileTool(access=access)]),
        verifier=EditVerifier([], scope=FileScopeCheck(tmp_path, ["allowed.py"])),
        recorder=recorder,
    )

    assert loop.run("edit only allowed.py") == "done"
    assert (tests / "test_tools.py").read_text(encoding="utf-8") == "original"
    assert (tmp_path / "allowed.py").read_text(encoding="utf-8") == "new"
    assert "outside allowed write set" in provider.results[0][1]
    assert "[verify PASS] file scope" in provider.results[1][1]
    assert [event.kind for event in recorder.events] == [
        "tool_call", "tool_call", "verify",
    ]


def test_verifier_runs_all_selected_commands_and_reports_status():
    outcomes = iter([CommandResult(1, "first failed"), CommandResult(0, "second passed")])
    sandbox = FakeSandbox(lambda: next(outcomes))
    verifier = EditVerifier(["check one", "check two"], sandbox)

    result = verifier.run()
    assert not result.passed
    assert "[verify FAIL] check one (exit=1)" in result.output
    assert "[verify PASS] check two (exit=0)" in result.output
    assert sandbox.calls == [("check one", 120), ("check two", 120)]


def test_scope_failure_is_fed_back_and_new_file_can_be_deleted(tmp_path):
    (tmp_path / "allowed.py").write_text("old", encoding="utf-8")
    scope = FileScopeCheck(tmp_path, ["allowed.py"])
    provider = ScriptedProvider([
        Turn("", [
            ToolCall("edit", "edit_file", {
                "path": "allowed.py", "old_string": "old", "new_string": "new",
            }),
            ToolCall("scratch", "write_file", {
                "path": "_verify.py", "content": "temporary",
            }),
        ]),
        Turn("", [ToolCall("remove", "delete_file", {"path": "_verify.py"})]),
        Turn("done", []),
    ])
    access = WorkspacePathPolicy(tmp_path)
    snapshots = SnapshotStore()
    loop = AgentLoop(
        provider,
        ToolRegistry([
            WriteFileTool(snapshots, access), EditFileTool(snapshots, access),
            DeleteFileTool(snapshots, access),
        ]),
        verifier=EditVerifier([], scope=scope),
    )

    assert loop.run("edit only allowed.py") == "done"
    assert (tmp_path / "allowed.py").read_text(encoding="utf-8") == "new"
    assert not (tmp_path / "_verify.py").exists()
    assert [call_id for call_id, _ in provider.results] == ["edit", "scratch", "remove"]
    assert "[verify" not in provider.results[0][1]
    assert "[verify FAIL] file scope: unexpected changes: _verify.py" in provider.results[1][1]
    assert "[verify PASS] file scope" in provider.results[2][1]


def test_scope_failure_for_changed_test_file_clears_after_revert(tmp_path):
    (tmp_path / "allowed.py").write_text("old", encoding="utf-8")
    tests = tmp_path / "tests"
    tests.mkdir()
    (tests / "test_tools.py").write_text("original", encoding="utf-8")
    scope = FileScopeCheck(tmp_path, ["allowed.py"])
    provider = ScriptedProvider([
        Turn("", [
            ToolCall("source", "edit_file", {
                "path": "allowed.py", "old_string": "old", "new_string": "new",
            }),
            ToolCall("test", "edit_file", {
                "path": "tests/test_tools.py", "old_string": "original", "new_string": "extra",
            }),
        ]),
        Turn("", [ToolCall("revert", "edit_file", {
            "path": "tests/test_tools.py", "old_string": "extra", "new_string": "original",
        })]),
        Turn("done", []),
    ])
    loop = AgentLoop(
        provider, ToolRegistry([EditFileTool(access=WorkspacePathPolicy(tmp_path))]),
        verifier=EditVerifier([], scope=scope),
    )

    assert loop.run("edit only allowed.py") == "done"
    assert (tmp_path / "allowed.py").read_text(encoding="utf-8") == "new"
    assert (tests / "test_tools.py").read_text(encoding="utf-8") == "original"
    assert "tests/test_tools.py" in provider.results[1][1]
    assert "[verify PASS] file scope" in provider.results[2][1]


def test_scope_detects_deleted_or_changed_files_and_ignores_agent_artifacts(tmp_path):
    allowed = tmp_path / "allowed.py"
    other = tmp_path / "other.py"
    artifact = tmp_path / "trace.jsonl"
    allowed.write_text("old", encoding="utf-8")
    other.write_text("stable", encoding="utf-8")
    scope = FileScopeCheck(tmp_path, ["allowed.py"], ignored_files=(str(artifact),))

    allowed.write_text("new", encoding="utf-8")
    artifact.write_text("trace", encoding="utf-8")
    assert scope.unexpected_changes() == []
    other.write_text("changed", encoding="utf-8")
    assert scope.unexpected_changes() == ["other.py"]
    other.unlink()
    assert scope.unexpected_changes() == ["other.py"]


def test_scope_catches_files_created_by_verification_command(tmp_path):
    (tmp_path / "allowed.py").write_text("old", encoding="utf-8")
    scope = FileScopeCheck(tmp_path, ["allowed.py"])

    def command_with_side_effect():
        (tmp_path / "extra.py").write_text("new", encoding="utf-8")
        return CommandResult(0, "check passed")

    sandbox = FakeSandbox(command_with_side_effect)
    result = EditVerifier(["check"], sandbox, scope=scope).run()
    assert not result.passed
    assert "[verify PASS] check" in result.output
    assert "[verify FAIL] file scope: unexpected changes: extra.py" in result.output


def test_failed_verification_is_fed_back_and_next_edit_repairs_it(tmp_path):
    source = tmp_path / "source.txt"
    source.write_text("return 0", encoding="utf-8")
    sandbox = FakeSandbox(lambda: CommandResult(
        0 if source.read_text(encoding="utf-8") == "return 2" else 1,
        "1 passed" if source.read_text(encoding="utf-8") == "return 2" else "expected return 2",
    ))
    turns = [
        Turn("", [ToolCall("edit-1", "edit_file", {
            "path": "source.txt", "old_string": "return 0", "new_string": "return 1",
        })]),
        Turn("", [ToolCall("edit-2", "edit_file", {
            "path": "source.txt", "old_string": "return 1", "new_string": "return 2",
        })]),
        Turn("fixed", []),
    ]
    provider = ScriptedProvider(turns)
    recorder = TraceRecorder()
    loop = AgentLoop(
        provider, ToolRegistry([EditFileTool(access=WorkspacePathPolicy(tmp_path))]),
        verifier=EditVerifier(["python -m pytest tests/test_math.py -q"], sandbox),
        recorder=recorder,
    )

    assert loop.run("make the function return 2") == "fixed"
    assert source.read_text(encoding="utf-8") == "return 2"
    assert [call_id for call_id, _ in provider.results] == ["edit-1", "edit-2"]
    assert "[verify FAIL]" in provider.results[0][1]
    assert "expected return 2" in provider.results[0][1]
    assert "[verify PASS]" in provider.results[1][1]
    assert len(sandbox.calls) == 2
    assert [event.kind for event in recorder.events] == [
        "tool_call", "verify", "tool_call", "verify",
    ]


def test_one_verification_after_multi_edit_batch_preserves_result_pairs(tmp_path):
    sandbox = FakeSandbox(lambda: CommandResult(0, "2 passed"))
    provider = ScriptedProvider([
        Turn("", [
            ToolCall("write-a", "write_file", {"path": "a.txt", "content": "a"}),
            ToolCall("write-b", "write_file", {"path": "b.txt", "content": "b"}),
        ]),
        Turn("done", []),
    ])
    loop = AgentLoop(
        provider, ToolRegistry([WriteFileTool(access=WorkspacePathPolicy(tmp_path))]),
        verifier=EditVerifier(["python -m pytest -q"], sandbox),
    )

    assert loop.run("write both files") == "done"
    assert len(sandbox.calls) == 1
    assert [call_id for call_id, _ in provider.results] == ["write-a", "write-b"]
    assert "[verify" not in provider.results[0][1]
    assert "[verify PASS]" in provider.results[1][1]


def test_denied_edit_does_not_run_verification(tmp_path):
    sandbox = FakeSandbox(lambda: CommandResult(0, "passed"))
    provider = ScriptedProvider([
        Turn("", [ToolCall("bad", "write_file", {"path": ".env", "content": "x"})]),
        Turn("done", []),
    ])
    loop = AgentLoop(
        provider, ToolRegistry([WriteFileTool(access=WorkspacePathPolicy(tmp_path))]),
        verifier=EditVerifier(["python -m pytest -q"], sandbox),
    )

    assert loop.run("write") == "done"
    assert provider.results[0][1].startswith("Error: access denied")
    assert sandbox.calls == []


def test_final_answer_is_marked_unverified_when_checks_still_fail(tmp_path):
    sandbox = FakeSandbox(lambda: CommandResult(1, "assertion failed"))
    provider = ScriptedProvider([
        Turn("", [ToolCall("write", "write_file", {"path": "a.txt", "content": "bad"})]),
        Turn("done", []),
    ])
    loop = AgentLoop(
        provider, ToolRegistry([WriteFileTool(access=WorkspacePathPolicy(tmp_path))]),
        verifier=EditVerifier(["python -m pytest -q"], sandbox),
    )

    result = loop.run("write")
    assert "task not verified" in result
    assert "assertion failed" in result


def test_real_docker_verifier_uses_isolated_copy(tmp_path):
    required = os.getenv("MINIDEV_REQUIRE_DOCKER") == "1"
    if shutil.which("docker") is None:
        if required:
            pytest.fail("Docker is required for the verification CI job")
        pytest.skip("Docker is not installed")
    image = subprocess.run(
        ["docker", "image", "inspect", "mindev-verify:local"],
        capture_output=True, check=False,
    )
    if image.returncode:
        if required:
            pytest.fail("mindev-verify:local must be built for the verification CI job")
        pytest.skip("mindev-verify:local is not available locally")

    source = tmp_path / "source"
    source.mkdir()
    (source / "value.txt").write_text("bad", encoding="utf-8")
    (source / "test_value.py").write_text(
        "from pathlib import Path\n"
        "def test_value():\n"
        "    assert Path('value.txt').read_text() == 'good'\n",
        encoding="utf-8",
    )
    workspace = create_workspace(source, tmp_path / "isolated")
    verifier = EditVerifier(
        ["python -m pytest test_value.py -q"],
        DockerSandbox(host_dir=str(workspace), image="mindev-verify:local"),
    )

    failed = verifier.run()
    assert not failed.passed
    assert "[verify FAIL]" in failed.output
    (workspace / "value.txt").write_text("good", encoding="utf-8")
    passed = verifier.run()
    assert passed.passed
    assert "[verify PASS]" in passed.output
    assert (source / "value.txt").read_text(encoding="utf-8") == "bad"
