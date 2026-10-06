import os
import subprocess

from mindev.sandbox.docker import DockerSandbox
from mindev.sandbox.local import LocalSandbox
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
    s = DockerSandbox(image="python:3.13-slim", workspace="/ws", host_dir=str(tmp_path))
    cmd = s.build_command("echo hi")
    assert cmd[0] == "docker"
    assert "none" in cmd  # --network none
    assert f"{tmp_path}:/ws" in cmd  # bind mount
    assert cmd[-1] == "echo hi"


def test_docker_sandbox_missing_docker(monkeypatch):
    def fake_run(*a, **k):
        raise FileNotFoundError("docker")

    monkeypatch.setattr(subprocess, "run", fake_run)
    out = DockerSandbox().run("echo hi")
    assert "docker" in out and "not installed" in out
