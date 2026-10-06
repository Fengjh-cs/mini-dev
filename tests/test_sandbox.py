import os
import shutil
import subprocess

import pytest

from mindev.sandbox.docker import DockerSandbox
from mindev.sandbox.local import LocalSandbox
from mindev.sandbox.workspace import create_workspace
from mindev.tools.bash import BashTool


def test_local_sandbox_runs_echo():
    assert "hello" in LocalSandbox().run("echo hello")


def test_local_sandbox_uses_platform_shell_and_fixed_cwd(tmp_path):
    assert LocalSandbox.build_command("echo hi", "nt") == [
        "powershell.exe", "-NoLogo", "-NoProfile", "-NonInteractive", "-Command", "echo hi"]
    assert LocalSandbox.build_command("echo hi", "posix") == ["/bin/sh", "-c", "echo hi"]
    command = "(Get-Location).Path" if os.name == "nt" else "pwd"
    assert str(tmp_path).lower() in LocalSandbox(cwd=str(tmp_path)).run(command).lower()


def test_bash_tool_describes_actual_shell(tmp_path):
    local = BashTool(LocalSandbox(cwd=str(tmp_path))).schema()["function"]["description"]
    docker = BashTool(DockerSandbox(host_dir=str(tmp_path))).schema()["function"]["description"]
    assert ("PowerShell" if os.name == "nt" else "POSIX sh") in local
    assert "POSIX sh" in docker


def test_local_sandbox_empty_command():
    assert LocalSandbox().run("   ").startswith("Error")


def test_local_sandbox_truncates_long_output(monkeypatch):
    class FakeProc:
        stdout = "x" * 30_000
        stderr = ""

    monkeypatch.setattr(subprocess, "run", lambda *a, **k: FakeProc())
    out = LocalSandbox().run("anything")
    assert len(out) < 30_000
    assert "truncated" in out


def test_local_sandbox_timeout(monkeypatch):
    def fake_run(*a, **k):
        raise subprocess.TimeoutExpired(cmd="x", timeout=1)

    monkeypatch.setattr(subprocess, "run", fake_run)
    assert "timed out" in LocalSandbox().run("sleep 10", timeout=1)


def test_docker_sandbox_builds_command(tmp_path):
    s = DockerSandbox(host_dir=str(tmp_path), image="python:3.13-slim", workspace="/ws")
    cmd = s.build_command("echo hi")
    assert cmd[0] == "docker"
    assert "none" in cmd  # --network none
    assert f"type=bind,source={tmp_path},target=/ws" in cmd
    assert "--read-only" in cmd
    assert cmd[cmd.index("--pull") + 1] == "never"
    assert ["--cap-drop", "ALL"] == cmd[cmd.index("--cap-drop"):cmd.index("--cap-drop") + 2]
    assert cmd[-1] == "echo hi"


def test_docker_sandbox_missing_docker(monkeypatch, tmp_path):
    def fake_run(*a, **k):
        raise FileNotFoundError("docker")

    monkeypatch.setattr(subprocess, "run", fake_run)
    out = DockerSandbox(host_dir=str(tmp_path)).run("echo hi")
    assert "docker" in out and "not installed" in out


def test_docker_sandbox_reports_nonzero_exit(monkeypatch, tmp_path):
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: subprocess.CompletedProcess(
        args=[], returncode=125, stdout="", stderr="image missing"
    ))
    out = DockerSandbox(host_dir=str(tmp_path)).run("echo hi")
    assert out.startswith("Error: command exited with status 125")
    assert "image missing" in out


def test_docker_command_writes_only_to_isolated_copy(tmp_path):
    required = os.getenv("MINIDEV_REQUIRE_DOCKER") == "1"
    if shutil.which("docker") is None:
        if required:
            pytest.fail("Docker is required for the isolation CI job")
        pytest.skip("Docker is not installed")
    image = subprocess.run(
        ["docker", "image", "inspect", "python:3.13-slim"],
        capture_output=True, check=False,
    )
    if image.returncode:
        if required:
            pytest.fail("python:3.13-slim must be available for the isolation CI job")
        pytest.skip("python:3.13-slim is not available locally")

    source = tmp_path / "source"
    source.mkdir()
    (source / "app.txt").write_text("original", encoding="utf-8")
    workspace = create_workspace(source, tmp_path / "isolated")
    output = DockerSandbox(host_dir=str(workspace)).run(
        "echo changed > /workspace/app.txt; echo escaped > /outside.txt"
    )
    assert "read-only" in output.lower() or "permission denied" in output.lower()
    assert (workspace / "app.txt").read_text(encoding="utf-8").strip() == "changed"
    assert (source / "app.txt").read_text(encoding="utf-8") == "original"
    assert not (tmp_path / "outside.txt").exists()
