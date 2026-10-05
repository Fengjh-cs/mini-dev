from mindev.context.repomap import extract_symbols, list_source_files


def test_extract_symbols_javascript(tmp_path):
    p = tmp_path / "a.js"
    p.write_text("function foo() {}\nclass Bar {}\nconst x = 1;\n")
    pairs = {(s.kind, s.name) for s in extract_symbols(str(p))}
    assert ("function", "foo") in pairs
    assert ("class", "Bar") in pairs


def test_extract_symbols_go(tmp_path):
    p = tmp_path / "a.go"
    p.write_text("package main\n\nfunc foo() {}\n\ntype Bar struct {}\n")
    pairs = {(s.kind, s.name) for s in extract_symbols(str(p))}
    assert ("function", "foo") in pairs
    assert ("type", "Bar") in pairs


def test_list_source_files_includes_multiple_languages(tmp_path):
    (tmp_path / "a.py").write_text("")
    (tmp_path / "b.js").write_text("")
    (tmp_path / "c.go").write_text("")
    (tmp_path / "d.txt").write_text("")
    assert set(list_source_files(str(tmp_path))) == {"a.py", "b.js", "c.go"}


def test_extract_symbols_python_nested_quote_fstring(tmp_path):
    # PEP 701 nested quotes inside an f-string used to crash tree-sitter.
    # Python extraction now uses `ast`, which must handle this without issue.
    p = tmp_path / "nested.py"
    p.write_text("def f():\n    return f\"value: {d['key']}\"\n")
    syms = extract_symbols(str(p))
    assert any(s.name == "f" for s in syms)
