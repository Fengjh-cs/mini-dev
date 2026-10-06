"""Command-line entry point for mini-dev."""

import argparse
import os
import shutil
import sys
from pathlib import Path


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

    if args.checkpoint:
        print("Error: --checkpoint is unavailable for isolated runs; review the saved workspace instead.",
              file=sys.stderr)
        return 2
    if args.mcp:
        print("Error: host MCP servers are unavailable in isolated runs.", file=sys.stderr)
        return 2
    if not args.plan and not args.no_bash:
        if args.sandbox != "docker":
            print("Error: bash requires --sandbox docker; use --no-bash without Docker.",
                  file=sys.stderr)
            return 2
        if shutil.which("docker") is None:
            print("Error: Docker is required for bash; install Docker or use --no-bash.",
                  file=sys.stderr)
            return 2

    from .agent.loop import AgentLoop
    from .agent.permissions import Mode, PermissionPolicy
    from .agent.subagent import EXPLORE_INSTRUCTIONS, ExploreSubagent
    from .context.prompter import build_system_prompt
    from .context.repomap import RepoMap
    from .llm.openai import OpenAIProvider
    from .sandbox.docker import DockerSandbox
    from .sandbox.workspace import create_workspace
    from .tools.access import AccessDenied, WorkspacePathPolicy
    from .tools.bash import BashTool
    from .tools.edit import EditFileTool, WriteFileTool
    from .tools.explore import ExploreTool
    from .tools.read import ReadTool
    from .tools.registry import ToolRegistry
    from .tools.snapshot import SnapshotStore

    source = os.getcwd()
    try:
        workspace = create_workspace(source, args.output_dir)
    except (OSError, ValueError) as exc:
        print(f"Error: could not create isolated workspace: {exc}", file=sys.stderr)
        return 2

    file_access = WorkspacePathPolicy(workspace)

    def artifact_path(raw: str) -> str:
        path = Path(raw)
        return str(path) if path.is_absolute() else str(file_access.resolve(raw))

    try:
        session_path = artifact_path(args.session) if args.session else None
        trace_path = artifact_path(args.trace) if args.trace else None
    except AccessDenied as exc:
        print(f"Error: artifact path {exc}", file=sys.stderr)
        return 2

    mode = Mode.READONLY if args.plan else Mode.READWRITE
    repo_map = "" if args.no_repomap else RepoMap().build(str(workspace))
    on_token = None
    if args.stream:
        on_token = lambda token: print(token, end="", flush=True)
    provider = OpenAIProvider(
        model=args.model,
        system=build_system_prompt(repo_map, plan=args.plan),
        on_token=on_token,
    )

    session_store = None
    if session_path:
        from .agent.session import SessionStore

        session_store = SessionStore(session_path)
        session_store.load(provider)

    snapshots = SnapshotStore()
    registry_tools = [ReadTool(file_access)]
    if not args.plan:
        registry_tools += [
            WriteFileTool(snapshots, file_access),
            EditFileTool(snapshots, file_access),
        ]
        if not args.no_bash:
            registry_tools.append(BashTool(DockerSandbox(host_dir=str(workspace))))
        registry_tools.append(
            ExploreTool(
                ExploreSubagent(
                    lambda: OpenAIProvider(model=args.model, system=EXPLORE_INSTRUCTIONS),
                    ToolRegistry([ReadTool(file_access)]),
                )
            )
        )

    tools = ToolRegistry(registry_tools)

    approver = None if args.yes else _interactive_approve
    policy = PermissionPolicy(mode=mode, approver=approver)
    compact_threshold = args.compact_threshold if args.compact_threshold > 0 else None
    recorder = None
    if trace_path:
        from .agent.trace import TraceRecorder

        recorder = TraceRecorder(trace_path)
    loop = AgentLoop(
        provider,
        tools,
        observer=_print_tool_call,
        policy=policy,
        compact_threshold=compact_threshold,
        recorder=recorder,
    )

    task = " ".join(args.task)
    print(f"Task: {task}\n[mode: {mode.value}]\n[workspace: {workspace}]\n", flush=True)
    try:
        result = loop.run(task)
    finally:
        if session_store is not None:
            session_store.save(provider)
    print("\n" + "=" * 40)
    print(result)
    if recorder is not None:
        s = recorder.summarize()
        print(
            f"\n[trace] {s['tool_calls']} tool calls, "
            f"{s['total_ms']} ms, {s['events']} events"
        )
    return 0


def _cmd_eval(args: argparse.Namespace) -> int:
    from dotenv import load_dotenv

    load_dotenv()

    if shutil.which("docker") is None:
        print("Error: Docker is required for the built-in bash evaluation task.",
              file=sys.stderr)
        return 2

    if not os.getenv("OPENAI_API_KEY"):
        print(
            "Error: OPENAI_API_KEY is not set. Copy .env.example to .env and "
            "add your OpenAI API key.",
            file=sys.stderr,
        )
        return 1

    import tempfile

    from .eval import LLMJudge, default_tasks, run_eval, summarize
    from .llm.openai import OpenAIProvider

    judge = LLMJudge(lambda: OpenAIProvider(model=args.model)) if args.judge else None
    with tempfile.TemporaryDirectory() as root:
        results = run_eval(
            lambda: OpenAIProvider(model=args.model),
            default_tasks(),
            root,
            judge=judge,
        )

    s = summarize(results)
    for r in results:
        score = f"  score={r.score:.1f}" if r.score is not None else ""
        print(f"  [{'PASS' if r.passed else 'FAIL'}] {r.name}{score}")
    line = f"\n{s['passed']}/{s['total']} passed"
    if s["avg_score"] is not None:
        line += f", avg score {s['avg_score']:.2f}"
    print(line)
    return 0 if s["passed"] == s["total"] else 1


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
        default="docker",
        help="Docker is required for bash; local is only valid with --no-bash.",
    )
    run_p.add_argument(
        "--output-dir", metavar="DIR",
        help="Create the isolated workspace at DIR (must not already exist).",
    )
    run_p.add_argument(
        "--no-bash",
        action="store_true",
        help="Disable the command tool (file reading and editing remain available).",
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
        "--stream",
        action="store_true",
        help="Stream the model's tokens as they are generated.",
    )
    run_p.add_argument(
        "--checkpoint",
        action="store_true",
        help="Unavailable in isolated runs; review the saved workspace instead.",
    )
    run_p.add_argument(
        "--compact-threshold",
        type=int,
        default=20000,
        help="Auto-compact history when context exceeds this many tokens "
        "(0 disables). Default: 20000.",
    )
    run_p.add_argument(
        "--session",
        default=None,
        metavar="FILE",
        help="Persist the conversation to FILE and resume it on the next run.",
    )
    run_p.add_argument(
        "--trace",
        default=None,
        metavar="FILE",
        help="Write a JSONL trace of tool calls to FILE.",
    )
    run_p.add_argument(
        "--mcp",
        action="append",
        default=[],
        metavar="COMMAND",
        help="Unavailable in isolated runs because MCP servers execute on the host.",
    )
    run_p.set_defaults(func=_cmd_run)

    eval_p = sub.add_parser("eval", help="Run the built-in evaluation tasks.")
    eval_p.add_argument("--model", default=None, help="Override the OpenAI model.")
    eval_p.add_argument(
        "--judge",
        action="store_true",
        help="Score outputs with an LLM judge (needs an API key).",
    )
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
