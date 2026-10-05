"""Generate a token-budgeted map of a repository (Aider-style RepoMap).

Extracts top-level function/class/type definitions so the agent gets a
condensed "what's here and where" instead of full file contents.

Python uses the stdlib ``ast`` module (robust, no native crash risk); JS/Go
use tree-sitter.
"""

import ast
import os
from dataclasses import dataclass

import tree_sitter_go
import tree_sitter_javascript
from tree_sitter import Language, Parser

IGNORED_DIRS = {
    ".git", ".venv", "venv", "__pycache__", "node_modules",
    ".idea", ".vscode", ".pytest_cache", ".mypy_cache", "dist", "build",
    "htmlcov", ".eggs",
}

# extension -> (language, {node_type -> symbol kind}) for non-Python languages
_LANGUAGES = {
    ".js": (
        Language(tree_sitter_javascript.language()),
        {"function_declaration": "function", "class_declaration": "class"},
    ),
    ".go": (
        Language(tree_sitter_go.language()),
        {
            "function_declaration": "function",
            "method_declaration": "function",
            "type_spec": "type",
        },
    ),
}

SOURCE_EXTENSIONS = {".py", ".js", ".go"}

_parsers: dict[str, Parser] = {}


def _parser_for(ext: str) -> Parser:
    if ext not in _parsers:
        language, _ = _LANGUAGES[ext]
        _parsers[ext] = Parser(language)
    return _parsers[ext]


@dataclass
class Symbol:
    kind: str  # "function" | "class" | "type"
    name: str
    line: int


def estimate_tokens(text: str) -> int:
    """Rough token estimate (4 chars ~ 1 token)."""
    return len(text) // 4


def list_source_files(root: str) -> list[str]:
    files: list[str] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(
            d for d in dirnames if d not in IGNORED_DIRS and not d.startswith(".")
        )
        for fn in sorted(filenames):
            if os.path.splitext(fn)[1] in SOURCE_EXTENSIONS:
                files.append(os.path.relpath(os.path.join(dirpath, fn), root))
    return files


def extract_symbols(path: str) -> list[Symbol]:
    ext = os.path.splitext(path)[1]
    if ext not in SOURCE_EXTENSIONS:
        return []
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            code = f.read()
    except OSError:
        return []
    if ext == ".py":
        return _extract_python(code)
    return _extract_tree_sitter(ext, code.encode("utf-8"))


def _extract_python(code: str) -> list[Symbol]:
    try:
        tree = ast.parse(code)
    except (SyntaxError, ValueError):
        return []
    symbols: list[Symbol] = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            symbols.append(Symbol(kind="function", name=node.name, line=node.lineno))
        elif isinstance(node, ast.ClassDef):
            symbols.append(Symbol(kind="class", name=node.name, line=node.lineno))
    return symbols


def _extract_tree_sitter(ext: str, data: bytes) -> list[Symbol]:
    tree = _parser_for(ext).parse(data)
    _, def_types = _LANGUAGES[ext]
    symbols: list[Symbol] = []

    def walk(node) -> None:
        kind = def_types.get(node.type)
        if kind is not None:
            name_node = node.child_by_field_name("name")
            if name_node is not None:
                name = data[name_node.start_byte:name_node.end_byte].decode("utf-8")
                symbols.append(
                    Symbol(kind=kind, name=name, line=node.start_point.row + 1)
                )
            return
        for child in node.children:
            walk(child)

    walk(tree.root_node)
    return symbols


class RepoMap:
    def __init__(self, max_tokens: int = 2000) -> None:
        self.max_tokens = max_tokens

    def build(self, root: str) -> str:
        label = os.path.basename(os.path.abspath(root)) or "."
        entries = [
            (rel, extract_symbols(os.path.join(root, rel)))
            for rel in list_source_files(root)
        ]
        text = self._render(entries, label)
        if estimate_tokens(text) <= self.max_tokens:
            return text

        # Over budget: drop symbol detail from the files with the most symbols
        # first, keeping their path in the tree (keeps the broadest structure).
        while estimate_tokens(text) > self.max_tokens:
            with_symbols = [(r, s) for r, s in entries if s]
            if not with_symbols:
                break
            rel, _ = max(with_symbols, key=lambda e: len(e[1]))
            entries = [(r, [] if r == rel else s) for r, s in entries]
            text = self._render(entries, label)

        # Bare file tree still too big: hard-truncate.
        if estimate_tokens(text) > self.max_tokens:
            text = text[: self.max_tokens * 4] + "\n... (truncated to token budget)"
        return text

    def _render(self, entries: list[tuple[str, list[Symbol]]], label: str) -> str:
        tree: dict = {}
        for rel, syms in entries:
            parts = rel.split(os.sep)
            node = tree
            for part in parts[:-1]:
                node = node.setdefault(part, {})
            node[parts[-1]] = syms
        lines = [label + "/"]
        self._emit(tree, lines, 0)
        return "\n".join(lines)

    def _emit(self, node: dict, lines: list[str], depth: int) -> None:
        indent = "  " * depth
        for name, value in sorted(node.items()):
            if isinstance(value, dict):
                lines.append(f"{indent}{name}/")
                self._emit(value, lines, depth + 1)
            else:
                lines.append(f"{indent}{name}")
                for sym in value:
                    lines.append(f"{indent}  {sym.kind} {sym.name}:{sym.line}")
