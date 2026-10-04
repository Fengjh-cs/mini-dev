"""Command-line entry point for mini-dev.

Phase 0: skeleton only. The agent loop, tools, and context modules are added
in later phases (see DESIGN.md for the roadmap).
"""

import argparse


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="mindev",
        description="mini-dev: a minimal CLI coding agent.",
    )
    parser.add_argument("--version", action="version", version="%(prog)s 0.1.0")
    parser.parse_args(argv)
    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
