"""Generate a token-budgeted map of a repository (Aider-style RepoMap).

Uses tree-sitter to extract top-level function/class definitions so the agent
gets a condensed "what's here and where" instead of full file contents.
"""

import os
from dataclasses import dataclass

import tree_sitter_python
from tree_sitter import Language, Parser

IGNORED_DIRS = {
    ".git", ".venv", "venv", "__pycache__", "node_modules",
    ".idea", ".vscode", ".pytest_cache", ".mypy_cache", "dist", "build",
    "htmlcov", ".eggs",
}

_PY_LANGUAGE = Language(tree_sitter_python.language())


@dataclass
class Symbol:
    kind: str  # "function" | "class"
    name: str
    line: int


def _parser() -> Parser:
    return Parser(_PY_LANGUAGE)


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
            if fn.endswith(".py"):
                files.append(os.path.relpath(os.path.join(dirpath, fn), root))
    return files


def extract_symbols(path: str) -> list[Symbol]:
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            code = f.read()
    except OSError:
        return []
    data = code.encode("utf-8")
    tree = _parser().parse(data)
    symbols: list[Symbol] = []

    def walk(node) -> None:
        if node.type in ("function_definition", "class_definition"):
            name_node = node.child_by_field_name("name")
            if name_node is not None:
                name = data[name_node.start_byte:name_node.end_byte].decode("utf-8")
                kind = "class" if node.type == "class_definition" else "function"
                symbols.append(
                    Symbol(kind=kind, name=name, line=node.start_point.row + 1)
                )
            return  # top-level only: don't descend into the definition body
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
