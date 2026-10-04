"""Assemble the system prompt sent to the model."""

BASE_INSTRUCTIONS = (
    "You are mini-dev, a coding agent. Complete the user's task by using the "
    "available tools to read files, edit files, and run commands, then summarize "
    "what you found or did. Use tools to gather real information instead of guessing."
)


def build_system_prompt(repo_map: str) -> str:
    if not repo_map.strip():
        return BASE_INSTRUCTIONS
    return (
        BASE_INSTRUCTIONS
        + "\n\nHere is a map of the repository (file tree plus top-level "
        + "function/class definitions with line numbers). Use it to locate "
        + "relevant code, then read the actual files before editing:\n\n"
        + repo_map
    )
