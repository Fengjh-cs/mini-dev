"""Command-line entry point for mini-dev."""

import argparse
import os
import shlex
import sys


def _print_tool_call(call) -> None:
    args = ", ".join(f"{k}={v!r}" for k, v in call.arguments.items())
    print(f"\n  -> {call.name}({args})", flush=True)


def _interactive_approve(tool_name: str, arguments: dict) -> bool:
    print(f"\n  [approval] run tool '{tool_name}' with arguments:")
    for key, value in arguments.items():
        print(f"      {key}: {value}")
    answer = input("      Approve? [y/N] ").strip().lower()
    return answer in ("y", "yes")


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
    from .agent.permissions import Mode, PermissionPolicy
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

    mode = Mode.READONLY if args.plan else Mode.READWRITE
    repo_map = "" if args.no_repomap else RepoMap().build(os.getcwd())
    provider = OpenAIProvider(
        model=args.model, system=build_system_prompt(repo_map, plan=args.plan)
    )

    snapshots = SnapshotStore()
    registry_tools = [ReadTool()]
    if not args.plan:
        sandbox = DockerSandbox() if args.sandbox == "docker" else LocalSandbox()
        registry_tools += [
            WriteFileTool(snapshots),
            EditFileTool(snapshots),
            BashTool(sandbox),
        ]

    mcp_clients = []
    if args.mcp:
        from .tools.mcp import McpClient, McpTool

        for spec in args.mcp:
            parts = shlex.split(spec)
            if not parts:
                continue
            client = McpClient(command=parts[0], args=parts[1:])
            mcp_clients.append(client)
            registry_tools += [McpTool(client, d) for d in client.list_tools()]

    tools = ToolRegistry(registry_tools)

    approver = None if args.yes else _interactive_approve
    policy = PermissionPolicy(mode=mode, approver=approver)
    loop = AgentLoop(provider, tools, observer=_print_tool_call, policy=policy)

    task = " ".join(args.task)
    print(f"Task: {task}\n[mode: {mode.value}]\n", flush=True)
    try:
        result = loop.run(task)
    finally:
        for client in mcp_clients:
            client.close()
    print("\n" + "=" * 40)
    print(result)
    return 0


def _cmd_eval(args: argparse.Namespace) -> int:
    from dotenv import load_dotenv

    load_dotenv()

    if not os.getenv("OPENAI_API_KEY"):
        print(
            "Error: OPENAI_API_KEY is not set. Copy .env.example to .env and "
            "add your OpenAI API key.",
            file=sys.stderr,
        )
        return 1

    import tempfile

    from .eval import default_tasks, run_eval
    from .llm.openai import OpenAIProvider

    with tempfile.TemporaryDirectory() as root:
        results = run_eval(
            lambda: OpenAIProvider(model=args.model), default_tasks(), root
        )

    passed = sum(1 for r in results if r.passed)
    for r in results:
        print(f"  [{'PASS' if r.passed else 'FAIL'}] {r.name}")
    print(f"\n{passed}/{len(results)} passed")
    return 0 if passed == len(results) else 1


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
    run_p.add_argument(
        "--plan",
        action="store_true",
        help="Read-only plan mode: explore and produce a plan, make no changes.",
    )
    run_p.add_argument(
        "--yes",
        action="store_true",
        help="Auto-approve all risky tool calls (skip confirmation).",
    )
    run_p.add_argument(
        "--mcp",
        action="append",
        default=[],
        metavar="COMMAND",
        help="Connect to an MCP stdio server (repeatable). E.g. 'npx -y "
        "@modelcontextprotocol/server-filesystem .'",
    )
    run_p.set_defaults(func=_cmd_run)

    eval_p = sub.add_parser("eval", help="Run the built-in evaluation tasks.")
    eval_p.add_argument("--model", default=None, help="Override the OpenAI model.")
    eval_p.set_defaults(func=_cmd_eval)

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
