"""Command-line entry point for mini-dev."""

import argparse
import os
import sys


def _print_tool_call(call) -> None:
    args = ", ".join(f"{k}={v!r}" for k, v in call.arguments.items())
    print(f"\n  -> {call.name}({args})", flush=True)


def _cmd_run(args: argparse.Namespace) -> int:
    from dotenv import load_dotenv

    load_dotenv()

    if not os.getenv("OPENAI_API_KEY"):
        print(
            "Error: OPENAI_API_KEY is not set. Copy .env.example to .env and "
            "add your OpenAI API key.",
            file=sys.stderr,
        )
        return 1

    from .agent.loop import AgentLoop
    from .context.prompter import build_system_prompt
    from .context.repomap import RepoMap
    from .llm.openai import OpenAIProvider
    from .sandbox.docker import DockerSandbox
    from .sandbox.local import LocalSandbox
    from .tools.bash import BashTool
    from .tools.edit import EditFileTool, WriteFileTool
    from .tools.read import ReadTool
    from .tools.registry import ToolRegistry
    from .tools.snapshot import SnapshotStore

    repo_map = "" if args.no_repomap else RepoMap().build(os.getcwd())
    provider = OpenAIProvider(model=args.model, system=build_system_prompt(repo_map))
    snapshots = SnapshotStore()
    sandbox = DockerSandbox() if args.sandbox == "docker" else LocalSandbox()
    tools = ToolRegistry(
        [
            ReadTool(),
            WriteFileTool(snapshots),
            EditFileTool(snapshots),
            BashTool(sandbox),
        ]
    )
    loop = AgentLoop(provider, tools, observer=_print_tool_call)

    task = " ".join(args.task)
    print(f"Task: {task}\n", flush=True)
    result = loop.run(task)
    print("\n" + "=" * 40)
    print(result)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mindev",
        description="mini-dev: a minimal CLI coding agent.",
    )
    parser.add_argument("--version", action="version", version="%(prog)s 0.1.0")

    sub = parser.add_subparsers(dest="command")

    run_p = sub.add_parser("run", help="Run a coding task.")
    run_p.add_argument("task", nargs="+", help="The task to perform.")
    run_p.add_argument("--model", default=None, help="Override the OpenAI model.")
    run_p.add_argument(
        "--sandbox",
        choices=["local", "docker"],
        default="local",
        help="Where to run bash commands (default: local).",
    )
    run_p.add_argument(
        "--no-repomap",
        action="store_true",
        help="Don't inject a repo map into the system prompt.",
    )
    run_p.set_defaults(func=_cmd_run)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    func = getattr(args, "func", None)
    if func is not None:
        return func(args)
    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
