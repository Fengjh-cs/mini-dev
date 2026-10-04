import os

from mindev.context.repomap import (
    RepoMap,
    estimate_tokens,
    extract_symbols,
    list_source_files,
)


def test_extract_symbols_top_level(tmp_path):
    p = tmp_path / "sample.py"
    p.write_text("def hello():\n    return 1\n\nclass Foo:\n    def bar(self):\n        pass\n")
    syms = extract_symbols(str(p))
    pairs = {(s.kind, s.name) for s in syms}
    assert ("function", "hello") in pairs
    assert ("class", "Foo") in pairs
    # methods are not top-level, so "bar" must not appear
    assert not any(s.name == "bar" for s in syms)


def test_extract_symbols_handles_non_ascii_before_symbol(tmp_path):
    # multi-byte text before the def must not break byte-offset slicing
    p = tmp_path / "u.py"
    p.write_text("# 中文注释\n\n\ndef hello():\n    return 1\n")
    syms = extract_symbols(str(p))
    assert any(s.name == "hello" for s in syms)


def test_list_source_files(tmp_path):
    (tmp_path / "a.py").write_text("")
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "b.py").write_text("")
    (tmp_path / "notes.txt").write_text("")
    (tmp_path / "__pycache__").mkdir()
    (tmp_path / "__pycache__" / "c.py").write_text("")
    assert set(list_source_files(str(tmp_path))) == {"a.py", os.path.join("sub", "b.py")}


def test_repomap_includes_symbols_within_budget(tmp_path):
    (tmp_path / "mod.py").write_text("def hello():\n    return 1\n")
    m = RepoMap(max_tokens=2000).build(str(tmp_path))
    assert "mod.py" in m
    assert "hello" in m
    assert "truncated" not in m


def test_repomap_is_much_smaller_than_source(tmp_path):
    body = "\n".join(f"    x{i} = {i}" for i in range(1000))
    (tmp_path / "big.py").write_text(f"def big_function():\n{body}\n")
    source = (tmp_path / "big.py").read_text()
    m = RepoMap(max_tokens=2000).build(str(tmp_path))
    assert "big_function" in m
    assert len(m) < len(source) // 10


def test_repomap_enforces_budget(tmp_path):
    for i in range(100):
        (tmp_path / f"f{i}.py").write_text(f"def function_{i}():\n    return {i}\n")
    m = RepoMap(max_tokens=50).build(str(tmp_path))
    # allow a little slack for the truncation note
    assert estimate_tokens(m) <= 50 + 20
