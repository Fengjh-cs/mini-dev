"""Offline checks for the isolated real-task runner."""

import subprocess

from validation import run_case


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
    assert run_case.classify({"exit_code": 1, "timed_out": False}, ok,
                             changes, ["allowed.py"])[0] == "invalid"
    assert run_case.classify(ok, {"exit_code": 1, "timed_out": False},
                             changes, ["allowed.py"])[1] == "failed"
    (checkout / "extra.py").write_text("x = 1\n", encoding="utf-8")
    changes = run_case.collect_changes(checkout, artifacts)
    assert changes["untracked_files"] == ["extra.py"]
    assert run_case.classify(ok, ok, changes, ["allowed.py"])[1] == "failed"
