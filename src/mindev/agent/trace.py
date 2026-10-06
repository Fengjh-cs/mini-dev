"""Lightweight tracing: record tool calls and compactions for later analysis."""

import json
from dataclasses import asdict, dataclass


@dataclass
class TraceEvent:
    kind: str  # "tool_call" | "compact" | "verify"
    name: str
    duration_ms: int
    tokens: int
    args: dict | None = None
    result: str = ""
    tokens_before: int | None = None


class TraceRecorder:
    def __init__(self, path: str | None = None) -> None:
        self._path = path
        self.events: list[TraceEvent] = []

    def record(self, event: TraceEvent) -> None:
        self.events.append(event)
        if self._path:
            with open(self._path, "a", encoding="utf-8") as f:
                f.write(json.dumps(asdict(event), ensure_ascii=False) + "\n")

    def summarize(self) -> dict:
        tool_calls = [e for e in self.events if e.kind == "tool_call"]
        return {
            "events": len(self.events),
            "tool_calls": len(tool_calls),
            "total_ms": sum(e.duration_ms for e in self.events),
        }
