"""Assemble the system prompt sent to the model."""

BASE_INSTRUCTIONS = (
    "You are mini-dev, a coding agent. Complete the user's task by using the "
    "available tools to read files, edit files, and run commands, then summarize "
    "what you found or did. Use tools to gather real information instead of guessing."
)

PLAN_INSTRUCTIONS = (
    "You are mini-dev in PLAN mode (read-only). Explore the repository and "
    "produce a clear step-by-step plan for the user's task. Do NOT modify files "
    "or run commands; only read and plan."
)


def build_system_prompt(repo_map: str, plan: bool = False) -> str:
    base = PLAN_INSTRUCTIONS if plan else BASE_INSTRUCTIONS
    if not repo_map.strip():
        return base
    return (
        base
        + "\n\nHere is a map of the repository (file tree plus top-level "
        + "function/class definitions with line numbers). Use it to locate "
        + "relevant code, then read the actual files before editing:\n\n"
        + repo_map
    )
