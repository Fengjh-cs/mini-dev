"""Private deterministic checks for the automatic real-task cases.

Run this file in a separate process with the candidate checkout's src first on
PYTHONPATH. The case prompts and this checker are absent from that checkout.
"""

import argparse
import json
import os
import subprocess
import tempfile
from pathlib import Path


AUTOMATIC_IDS = {1, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15}


def _expect(failures: list[str], condition: bool, message: str) -> None:
    if not condition:
        failures.append(message)


def _exact_replacement(checkout: Path, baseline: str, rel: str,
                       old: str, new: str, failures: list[str]) -> None:
    original = subprocess.run(
        ["git", "show", f"{baseline}:{rel}"], cwd=checkout, check=True,
        capture_output=True, text=True, encoding="utf-8",
    ).stdout
    current = (checkout / rel).read_text(encoding="utf-8")
    _expect(failures, original.count(old) == 1, "checker baseline mismatch")
    _expect(failures, current == original.replace(old, new, 1),
            "source differs from the single requested replacement")


def _check_1(failures: list[str], scratch: Path) -> None:
    from mindev.tools.read import read_lines

    path = scratch / "lines.txt"
    path.write_text("alpha\nbeta\ngamma\n", encoding="utf-8")
    two = str(read_lines(str(path), 2))
    all_lines = str(read_lines(str(path), 10))
    zero = str(read_lines(str(path), 0))
    _expect(failures, "alpha" in two and "beta" in two and "gamma" not in two
            and two.index("alpha") < two.index("beta"), "n=2 should return first two lines in order")
    _expect(failures, all(x in all_lines for x in ("alpha", "beta", "gamma")),
            "n greater than file length should return all lines")
    _expect(failures, "alpha" not in zero, "n=0 should return no file content")
    try:
        missing = str(read_lines(str(scratch / "missing.txt"), 2)).lower()
    except Exception as exc:
        failures.append(f"missing file raised {type(exc).__name__}")
    else:
        _expect(failures, any(x in missing for x in ("error", "not found", "不存在", "找不到")),
                "missing file should return a recognizable error")


def _check_3(failures: list[str], checkout: Path, baseline: str, scratch: Path) -> None:
    _exact_replacement(checkout, baseline, "src/mindev/tools/read.py",
                       "MAX_OUTPUT_CHARS = 20_000", "MAX_OUTPUT_CHARS = 10_000", failures)
    from mindev.tools.read import ReadTool

    path = scratch / "long.txt"
    path.write_text("x" * 11_000, encoding="utf-8")
    output = ReadTool().run({"path": str(path)})
    expected = ("   1 " + "x" * 11_000)[:10_000] + "\n... (truncated)"
    _expect(failures, output == expected, "read output should truncate at 10000 characters")


def _check_6(failures: list[str], scratch: Path) -> None:
    from mindev.tools.edit import WriteFileTool

    path = scratch / "new" / "nested" / "file.txt"
    tool = WriteFileTool()
    tool.run({"path": str(path), "content": "first"})
    _expect(failures, path.exists() and path.read_text(encoding="utf-8") == "first",
            "nested write should create parent directories and file")
    tool.run({"path": str(path), "content": "second"})
    _expect(failures, path.read_text(encoding="utf-8") == "second",
            "existing file should still be overwritten")


def _check_7(failures: list[str], scratch: Path) -> None:
    from mindev.tools.edit import EditFileTool
    from mindev.tools.snapshot import SnapshotStore

    path = scratch / "same.txt"
    path.write_text("before", encoding="utf-8")
    os.utime(path, (1, 1))
    original_mtime = path.stat().st_mtime_ns
    snapshots = SnapshotStore()
    output = EditFileTool(snapshots).run(
        {"path": str(path), "old_string": "before", "new_string": "before"}
    ).lower()
    _expect(failures, any(x in output for x in ("no-op", "noop", "no change", "unchanged", "未修改")),
            "same-text edit should report a no-op")
    _expect(failures, path.read_text(encoding="utf-8") == "before",
            "same-text edit should preserve content")
    _expect(failures, path.stat().st_mtime_ns == original_mtime,
            "same-text edit should not write the file")
    _expect(failures, not snapshots._states, "same-text edit should not create a snapshot")


def _check_8(failures: list[str], scratch: Path) -> None:
    from mindev.tools.snapshot import SnapshotStore

    path = scratch / "snapshot.txt"
    path.write_text("before", encoding="utf-8")
    store = SnapshotStore()
    _expect(failures, store.has_snapshot(str(path)) is False, "initial snapshot state")
    store.snapshot(str(path))
    _expect(failures, store.has_snapshot(str(path)) is True, "state after snapshot")
    path.write_text("after", encoding="utf-8")
    store.restore(str(path))
    _expect(failures, store.has_snapshot(str(path)) is False, "state after restore")
    _expect(failures, path.read_text(encoding="utf-8") == "before", "restore behavior")


def _check_9(failures: list[str]) -> None:
    from mindev.tools.read import ReadTool
    from mindev.tools.registry import ToolRegistry

    try:
        ToolRegistry([ReadTool(), ReadTool()])
    except ValueError:
        pass
    else:
        failures.append("duplicate tool names should raise ValueError")
    _expect(failures, len(ToolRegistry([ReadTool()]).schemas()) == 1,
            "single tool registration should still work")


def _check_10(failures: list[str]) -> None:
    from mindev.agent.trace import TraceEvent, TraceRecorder

    recorder = TraceRecorder()
    recorder.record(TraceEvent("compact", "compact", 0, 5))
    recorder.record(TraceEvent("tool_call", "read_file", 2, 6))
    recorder.record(TraceEvent("compact", "compact", 0, 4))
    summary = recorder.summarize()
    _expect(failures, summary.get("compact_events") == 2, "compact_events should count compactions")
    _expect(failures, summary.get("tool_calls") == 1 and summary.get("events") == 3,
            "existing summary fields should remain correct")


def _check_11(failures: list[str], scratch: Path) -> None:
    from mindev.agent.trace import TraceEvent, TraceRecorder

    path = scratch / "trace.jsonl"
    recorder = TraceRecorder(str(path))
    recorder.record(TraceEvent("tool_call", "read_file", 2, 6))
    recorder.clear()
    _expect(failures, recorder.events == [], "clear should empty in-memory events")
    _expect(failures, len(path.read_text(encoding="utf-8").splitlines()) == 1,
            "clear should preserve existing trace file")
    recorder.record(TraceEvent("compact", "compact", 0, 4))
    _expect(failures, recorder.summarize()["events"] == 1,
            "record should still work after clear")
    _expect(failures, len(path.read_text(encoding="utf-8").splitlines()) == 2,
            "new record should append to existing file")


def _check_12(failures: list[str], scratch: Path) -> None:
    from mindev.agent.session import SessionStore

    path = scratch / "session.json"
    path.write_text("{}", encoding="utf-8")
    store = SessionStore(str(path))
    store.delete()
    _expect(failures, not path.exists() and not store.exists(), "delete should remove session")
    store.delete()


def _check_13(failures: list[str]) -> None:
    from mindev.agent.permissions import Mode, PermissionPolicy

    act = PermissionPolicy(mode=Mode.READWRITE)
    plan = PermissionPolicy(mode=Mode.READONLY)
    _expect(failures, act.allow("other", "network", {}) is False,
            "unknown risk should be denied in readwrite mode")
    _expect(failures, plan.allow("other", "network", {}) is False,
            "unknown risk should be denied in readonly mode")
    _expect(failures, act.allow("read_file", "read", {}) is True
            and act.allow("bash", "command", {}) is True,
            "known risks should keep existing readwrite behavior")
    _expect(failures, plan.allow("bash", "command", {}) is False,
            "known risks should keep existing readonly behavior")


def _check_14(failures: list[str], scratch: Path) -> None:
    from mindev.context.repomap import RepoMap, extract_symbols, list_source_files

    path = scratch / "types.pyi"
    path.write_text("class Widget: ...\ndef make() -> Widget: ...\n", encoding="utf-8")
    _expect(failures, "types.pyi" in list_source_files(str(scratch)),
            ".pyi should appear in source list")
    names = {symbol.name for symbol in extract_symbols(str(path))}
    _expect(failures, {"Widget", "make"} <= names,
            ".pyi should expose top-level class and function symbols")
    repomap = RepoMap().build(str(scratch))
    _expect(failures, "types.pyi" in repomap and "Widget" in repomap and "make" in repomap,
            "RepoMap should render .pyi symbols")


def _check_15(failures: list[str]) -> None:
    from mindev.tools.read import ReadTool
    from mindev.tools.registry import ToolRegistry

    class Z(ReadTool):
        name = "zeta"

    class A(ReadTool):
        name = "alpha"

    registry = ToolRegistry([Z(), A()])
    _expect(failures, registry.names() == ["alpha", "zeta"],
            "names should return alphabetically sorted tool names")
    _expect(failures, [s["function"]["name"] for s in registry.schemas()] == ["zeta", "alpha"],
            "schemas should preserve registration order")


def check_case(case_id: int, checkout: Path, baseline: str, scratch_root: Path) -> dict:
    if case_id not in AUTOMATIC_IDS:
        raise ValueError("This case requires manual review")
    failures: list[str] = []
    with tempfile.TemporaryDirectory(dir=scratch_root) as temp:
        scratch = Path(temp)
        try:
            if case_id == 1:
                _check_1(failures, scratch)
            elif case_id == 3:
                _check_3(failures, checkout, baseline, scratch)
            elif case_id == 4:
                _exact_replacement(checkout, baseline, "src/mindev/tools/edit.py",
                                   "MAX_EDIT_CHARS = 100_000", "MAX_EDIT_CHARS = 50_000", failures)
            elif case_id == 5:
                _exact_replacement(checkout, baseline, "src/mindev/sandbox/local.py",
                                   "MAX_OUTPUT_CHARS = 20_000", "MAX_OUTPUT_CHARS = 10_000", failures)
            elif case_id == 6:
                _check_6(failures, scratch)
            elif case_id == 7:
                _check_7(failures, scratch)
            elif case_id == 8:
                _check_8(failures, scratch)
            elif case_id == 9:
                _check_9(failures)
            elif case_id == 10:
                _check_10(failures)
            elif case_id == 11:
                _check_11(failures, scratch)
            elif case_id == 12:
                _check_12(failures, scratch)
            elif case_id == 13:
                _check_13(failures)
            elif case_id == 14:
                _check_14(failures, scratch)
            elif case_id == 15:
                _check_15(failures)
        except Exception as exc:
            failures.append(f"{type(exc).__name__}: {exc}")
    return {"case": case_id, "passed": not failures, "failures": failures}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", type=int, required=True, choices=sorted(AUTOMATIC_IDS))
    parser.add_argument("--checkout", type=Path, required=True)
    parser.add_argument("--baseline", required=True)
    parser.add_argument("--scratch-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = check_case(args.case, args.checkout, args.baseline, args.scratch_root)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
