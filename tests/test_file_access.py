"""Negative checks for the model-facing file tools' workspace boundary."""

import os
import subprocess
from unittest.mock import patch

import pytest

from mindev.tools.access import WorkspacePathPolicy
from mindev.tools.edit import DeleteFileTool, EditFileTool, WriteFileTool
from mindev.tools.read import ReadTool
from mindev.tools.snapshot import SnapshotStore


def _assert_denied_by_all_file_tools(path, access):
    snapshots = SnapshotStore()
    read_result = ReadTool(access).run({"path": str(path)})
    write_result = WriteFileTool(snapshots, access).run(
        {"path": str(path), "content": "overwritten"}
    )
    edit_result = EditFileTool(snapshots, access).run(
        {"path": str(path), "old_string": "sentinel", "new_string": "overwritten"}
    )
    delete_result = DeleteFileTool(snapshots, access).run({"path": str(path)})
    for result in (read_result, write_result, edit_result, delete_result):
        assert result.startswith("Error: access denied"), result
        assert "sentinel" not in result
    assert not snapshots._states


@pytest.mark.parametrize("name", [".env", ".env.local", "nested/.env.production"])
def test_environment_files_are_denied(tmp_path, name):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    secret = workspace / name
    secret.parent.mkdir(parents=True, exist_ok=True)
    secret.write_text("sentinel=synthetic-test-value", encoding="utf-8")
    access = WorkspacePathPolicy(workspace)

    _assert_denied_by_all_file_tools(name, access)
    _assert_denied_by_all_file_tools(secret, access)
    assert secret.read_text(encoding="utf-8") == "sentinel=synthetic-test-value"


@pytest.mark.parametrize("alias", [".ENV", ".env.", ".env ", ".env::$DATA"])
def test_environment_file_aliases_are_denied(tmp_path, alias):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    secret = workspace / ".env"
    secret.write_text("sentinel=synthetic-test-value", encoding="utf-8")

    _assert_denied_by_all_file_tools(alias, WorkspacePathPolicy(workspace))
    assert secret.read_text(encoding="utf-8") == "sentinel=synthetic-test-value"


def test_relative_and_absolute_paths_outside_workspace_are_denied(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("sentinel=outside", encoding="utf-8")
    access = WorkspacePathPolicy(workspace)

    _assert_denied_by_all_file_tools("../outside.txt", access)
    _assert_denied_by_all_file_tools(outside, access)
    _assert_denied_by_all_file_tools("../new.txt", access)
    assert outside.read_text(encoding="utf-8") == "sentinel=outside"
    assert not (tmp_path / "new.txt").exists()


def _make_directory_link(link, target):
    try:
        link.symlink_to(target, target_is_directory=True)
    except (NotImplementedError, OSError) as exc:
        if os.name != "nt":
            pytest.skip(f"filesystem cannot create symlinks: {exc}")
        # Unprivileged Windows often forbids symlinks; directory junctions
        # exercise the same path-resolution escape without that privilege.
        result = subprocess.run(
            ["cmd.exe", "/c", "mklink", "/J", str(link), str(target)],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode:
            pytest.skip(f"filesystem cannot create a directory link: {result.returncode}")


def test_link_escape_read_and_write_are_denied(tmp_path):
    workspace = tmp_path / "workspace"
    outside = tmp_path / "outside"
    workspace.mkdir()
    outside.mkdir()
    secret = outside / "secret.txt"
    secret.write_text("sentinel=outside", encoding="utf-8")
    link = workspace / "link"
    _make_directory_link(link, outside)
    assert link.resolve() == outside.resolve()

    access = WorkspacePathPolicy(workspace)
    _assert_denied_by_all_file_tools("link/secret.txt", access)
    result = WriteFileTool(access=access).run(
        {"path": "link/new.txt", "content": "escaped"}
    )
    assert result.startswith("Error: access denied")
    assert secret.read_text(encoding="utf-8") == "sentinel=outside"
    assert not (outside / "new.txt").exists()


def test_ordinary_files_and_env_example_remain_accessible(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    access = WorkspacePathPolicy(workspace)
    example = workspace / ".env.example"
    example.write_text("KEY=placeholder", encoding="utf-8")

    assert "KEY=placeholder" in ReadTool(access).run({"path": ".env.example"})
    assert WriteFileTool(access=access).run(
        {"path": "notes.txt", "content": "before"}
    ).startswith("Wrote")
    assert EditFileTool(access=access).run(
        {"path": "notes.txt", "old_string": "before", "new_string": "after"}
    ).startswith("Edited")
    assert (workspace / "notes.txt").read_text(encoding="utf-8") == "after"
    assert DeleteFileTool(access=access).run({"path": "notes.txt"}).startswith("Deleted")
    assert not (workspace / "notes.txt").exists()


def test_allowed_write_set_rejects_every_mutation_before_open_or_snapshot(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    allowed = workspace / "allowed.py"
    restricted = workspace / "tests" / "test_tools.py"
    restricted.parent.mkdir()
    allowed.write_text("before", encoding="utf-8")
    restricted.write_text("sentinel", encoding="utf-8")
    access = WorkspacePathPolicy(workspace, allowed_writes=["allowed.py"])
    snapshots = SnapshotStore()

    # The write list must not hide unrelated files from the read tool.
    assert "sentinel" in ReadTool(access).run({"path": "tests/test_tools.py"})
    with patch("builtins.open") as opened:
        results = [
            WriteFileTool(snapshots, access).run(
                {"path": "tests/test_tools.py", "content": "changed"}),
            EditFileTool(snapshots, access).run(
                {"path": "tests/test_tools.py", "old_string": "sentinel", "new_string": "changed"}),
            DeleteFileTool(snapshots, access).run({"path": "tests/test_tools.py"}),
            WriteFileTool(snapshots, access).run(
                {"path": "scratch.py", "content": "new"}),
        ]
        opened.assert_not_called()

    assert all("outside allowed write set" in result for result in results)
    assert restricted.read_text(encoding="utf-8") == "sentinel"
    assert not (workspace / "scratch.py").exists()
    assert snapshots._states == {}


def test_allowed_write_set_accepts_only_named_files_and_canonical_aliases(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    access = WorkspacePathPolicy(workspace, allowed_writes=["allowed.py", "new.py"])
    write = WriteFileTool(access=access)

    assert write.run({"path": "./allowed.py", "content": "before"}).startswith("Wrote")
    assert EditFileTool(access=access).run({
        "path": str(workspace / "allowed.py"),
        "old_string": "before", "new_string": "after",
    }).startswith("Edited")
    assert write.run({"path": "new.py", "content": "new"}).startswith("Wrote")
    assert DeleteFileTool(access=access).run({"path": "new.py"}).startswith("Deleted")
    assert (workspace / "allowed.py").read_text(encoding="utf-8") == "after"
    assert not (workspace / "new.py").exists()


@pytest.mark.parametrize("allowed", [
    [], [""], ["../outside.py"], [".env"], ["nested"],
])
def test_invalid_allowed_write_set_is_rejected_at_construction(tmp_path, allowed):
    (tmp_path / "nested").mkdir()
    with pytest.raises(ValueError):
        WorkspacePathPolicy(tmp_path, allowed_writes=allowed)
