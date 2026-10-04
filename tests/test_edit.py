from mindev.tools.edit import EditFileTool, WriteFileTool
from mindev.tools.snapshot import SnapshotStore


def test_write_file_creates(tmp_path):
    p = tmp_path / "new.txt"
    out = WriteFileTool().run({"path": str(p), "content": "hello\n"})
    assert p.read_text() == "hello\n"
    assert "Wrote" in out


def test_write_file_overwrites(tmp_path):
    p = tmp_path / "a.txt"
    p.write_text("old")
    WriteFileTool().run({"path": str(p), "content": "new"})
    assert p.read_text() == "new"


def test_edit_file_replaces_unique_occurrence(tmp_path):
    p = tmp_path / "a.txt"
    p.write_text("def foo():\n    return 1\n")
    out = EditFileTool().run(
        {"path": str(p), "old_string": "return 1", "new_string": "return 2"}
    )
    assert p.read_text() == "def foo():\n    return 2\n"
    assert "Edited" in out


def test_edit_file_not_found_is_rejected(tmp_path):
    p = tmp_path / "a.txt"
    p.write_text("abc")
    out = EditFileTool().run({"path": str(p), "old_string": "zzz", "new_string": "x"})
    assert out.startswith("Error")
    assert p.read_text() == "abc"


def test_edit_file_non_unique_is_rejected(tmp_path):
    p = tmp_path / "a.txt"
    p.write_text("dup dup")
    out = EditFileTool().run({"path": str(p), "old_string": "dup", "new_string": "x"})
    assert "not unique" in out
    assert p.read_text() == "dup dup"


def test_edit_file_empty_old_string_rejected(tmp_path):
    p = tmp_path / "a.txt"
    p.write_text("abc")
    out = EditFileTool().run({"path": str(p), "old_string": "", "new_string": "x"})
    assert out.startswith("Error")


def test_snapshot_restores_modified_file(tmp_path):
    p = tmp_path / "a.txt"
    p.write_text("original")
    snap = SnapshotStore()
    snap.snapshot(str(p))
    p.write_text("changed")
    snap.restore(str(p))
    assert p.read_text() == "original"


def test_snapshot_restore_deletes_newly_created_file(tmp_path):
    p = tmp_path / "new.txt"
    snap = SnapshotStore()
    snap.snapshot(str(p))  # did not exist yet
    p.write_text("created")
    snap.restore(str(p))
    assert not p.exists()


def test_edit_tool_snapshots_before_edit(tmp_path):
    p = tmp_path / "a.txt"
    p.write_text("before")
    snap = SnapshotStore()
    EditFileTool(snap).run(
        {"path": str(p), "old_string": "before", "new_string": "after"}
    )
    assert p.read_text() == "after"
    snap.restore(str(p))
    assert p.read_text() == "before"
