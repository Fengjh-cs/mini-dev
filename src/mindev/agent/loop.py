"""The core agent loop.

Ask the model, run any tools it requests (subject to the permission policy),
feed results back, repeat until the model answers without a tool call.
"""

import time
from collections.abc import Callable

from ..llm.base import LLMProvider, ToolCall
from ..tools.registry import ToolRegistry
from .permissions import PermissionPolicy
from .trace import TraceEvent, TraceRecorder
from .verify import EditVerifier, VerificationResult

Observer = Callable[[ToolCall], None]


class AgentLoop:
    def __init__(
        self,
        provider: LLMProvider,
        tools: ToolRegistry,
        max_iterations: int = 30,
        observer: Observer | None = None,
        policy: PermissionPolicy | None = None,
        compact_threshold: int | None = None,
        compact_keep: int = 6,
        recorder: TraceRecorder | None = None,
        verifier: EditVerifier | None = None,
    ) -> None:
        self._provider = provider
        self._tools = tools
        self._max_iterations = max_iterations
        self._observer = observer
        self._policy = policy or PermissionPolicy()
        self._compact_threshold = compact_threshold
        self._compact_keep = compact_keep
        self._recorder = recorder
        self._verifier = verifier

    def run(self, task: str) -> str:
        self._provider.add_user(task)
        verification_failure: str | None = None
        for _ in range(self._max_iterations):
            if self._compact_threshold is not None:
                tokens_before = self._provider.context_tokens()
                if tokens_before > self._compact_threshold:
                    self._provider.compact(self._compact_keep)
                    self._record(
                        TraceEvent(
                            "compact", "compact", 0,
                            self._provider.context_tokens(),
                            tokens_before=tokens_before,
                        )
                    )
            turn = self._provider.send(self._tools.schemas())
            if not turn.tool_calls:
                answer = turn.text.strip() or "(no response)"
                if verification_failure:
                    return ("(verification failed; task not verified)\n"
                            + verification_failure + "\n\n" + answer)
                return answer
            results: list[tuple[str, str]] = []
            last_edit_index: int | None = None
            for call in turn.tool_calls:
                if self._policy.allow(call.name, self._tools.risk(call.name), call.arguments):
                    if self._observer:
                        self._observer(call)
                    start = time.monotonic()
                    output = self._tools.run(call.name, call.arguments)
                    duration_ms = int((time.monotonic() - start) * 1000)
                    self._record(
                        TraceEvent(
                            "tool_call",
                            call.name,
                            duration_ms,
                            self._provider.context_tokens(),
                            call.arguments,
                            output[:200],
                        )
                    )
                else:
                    output = f"DENIED: tool '{call.name}' was not approved."
                    self._record(
                        TraceEvent(
                            "tool_call",
                            call.name,
                            0,
                            self._provider.context_tokens(),
                            call.arguments,
                            "DENIED",
                        )
                    )
                results.append((call.id, output))
                if (self._verifier is not None and call.name in {"write_file", "edit_file"}
                        and output.startswith(("Wrote ", "Edited "))):
                    last_edit_index = len(results) - 1
            if last_edit_index is not None:
                start = time.monotonic()
                try:
                    verification = self._verifier.run()
                except Exception as exc:
                    verification = VerificationResult(False, f"[verify FAIL] runner error: {exc}")
                duration_ms = int((time.monotonic() - start) * 1000)
                verification_failure = None if verification.passed else verification.output
                call_id, output = results[last_edit_index]
                results[last_edit_index] = (call_id, output + "\n\n" + verification.output)
                self._record(
                    TraceEvent("verify", "tests", duration_ms,
                               self._provider.context_tokens(),
                               result=verification.output[:200])
                )
            for call_id, output in results:
                self._provider.add_tool_result(call_id, output)
        if verification_failure:
            return ("(reached the iteration limit; verification failed)\n"
                    + verification_failure)
        return "(reached the iteration limit before the task finished)"

    def _record(self, event: TraceEvent) -> None:
        if self._recorder is not None:
            self._recorder.record(event)
