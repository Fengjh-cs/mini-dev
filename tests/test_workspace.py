"""The agent's working tree must be a separate, credential-free copy."""

import os
import subprocess

import pytest

from mindev.sandbox.workspace import create_workspace


def test_copy_keeps_original_untouched_and_omits_private_files(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "app.py").write_text("before", encoding="utf-8")
    (source / ".env").write_text("synthetic-secret", encoding="utf-8")
    (source / ".env.local").write_text("another-secret", encoding="utf-8")
    (source / ".env.example").write_text("KEY=placeholder", encoding="utf-8")
    (source / ".git").mkdir()
    (source / ".git" / "config").write_text("git-config", encoding="utf-8")
    (source / ".venv").mkdir()
    (source / ".venv" / "marker").write_text("venv", encoding="utf-8")

    workspace = create_workspace(source, tmp_path / "isolated")
    assert workspace == tmp_path / "isolated"
    assert (workspace / "app.py").read_text(encoding="utf-8") == "before"
    assert (workspace / ".env.example").exists()
    assert not (workspace / ".env").exists()
    assert not (workspace / ".env.local").exists()
    assert not (workspace / ".git").exists()
    assert not (workspace / ".venv").exists()

    (workspace / "app.py").write_text("after", encoding="utf-8")
    assert (source / "app.py").read_text(encoding="utf-8") == "before"


def test_copy_rejects_destination_inside_source_before_creating_it(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    with pytest.raises(ValueError, match="outside the source tree"):
        create_workspace(source, source / "new-parent" / "copy")
    assert not (source / "new-parent").exists()


def test_copy_omits_link_to_outside(tmp_path):
    source = tmp_path / "source"
    outside = tmp_path / "outside"
    source.mkdir()
    outside.mkdir()
    (outside / "private.txt").write_text("outside", encoding="utf-8")
    link = source / "link"
    try:
        link.symlink_to(outside, target_is_directory=True)
    except (NotImplementedError, OSError) as exc:
        if os.name != "nt":
            pytest.skip(f"filesystem cannot create symlinks: {exc}")
        result = subprocess.run(
            ["cmd.exe", "/c", "mklink", "/J", str(link), str(outside)],
            capture_output=True, text=True, check=False,
        )
        if result.returncode:
            pytest.skip(f"filesystem cannot create a directory link: {result.returncode}")
    assert link.resolve() == outside.resolve()

    workspace = create_workspace(source, tmp_path / "isolated")
    assert not (workspace / "link").exists()
    assert (outside / "private.txt").read_text(encoding="utf-8") == "outside"


def test_copy_omits_link_back_to_source(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    link = source / "loop"
    try:
        link.symlink_to(source, target_is_directory=True)
    except (NotImplementedError, OSError) as exc:
        if os.name != "nt":
            pytest.skip(f"filesystem cannot create symlinks: {exc}")
        result = subprocess.run(
            ["cmd.exe", "/c", "mklink", "/J", str(link), str(source)],
            capture_output=True, text=True, check=False,
        )
        if result.returncode:
            pytest.skip(f"filesystem cannot create a directory link: {result.returncode}")

    workspace = create_workspace(source, tmp_path / "isolated")
    assert not (workspace / "loop").exists()
