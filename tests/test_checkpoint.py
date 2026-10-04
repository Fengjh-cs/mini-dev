import subprocess

from mindev.agent.checkpoint import GitCheckpoint


def _init_repo(path):
    subprocess.run(["git", "init", "-q"], cwd=str(path), check=True)
    subprocess.run(["git", "config", "user.email", "t@t.com"], cwd=str(path), check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=str(path), check=True)


def test_checkpoint_commits_dirty_tree(tmp_path):
    _init_repo(tmp_path)
    (tmp_path / "a.txt").write_text("v1")
    subprocess.run(["git", "add", "-A"], cwd=str(tmp_path), check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=str(tmp_path), check=True)

    (tmp_path / "a.txt").write_text("v2")
    h = GitCheckpoint(cwd=str(tmp_path)).commit()
    assert h is not None

    out = subprocess.run(
        ["git", "show", "HEAD:a.txt"], cwd=str(tmp_path), capture_output=True, text=True
    )
    assert out.stdout.strip() == "v2"


def test_checkpoint_clean_tree_returns_none(tmp_path):
    _init_repo(tmp_path)
    (tmp_path / "a.txt").write_text("v1")
    subprocess.run(["git", "add", "-A"], cwd=str(tmp_path), check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=str(tmp_path), check=True)

    assert GitCheckpoint(cwd=str(tmp_path)).commit() is None


def test_checkpoint_non_repo_returns_none(tmp_path):
    assert GitCheckpoint(cwd=str(tmp_path)).commit() is None
