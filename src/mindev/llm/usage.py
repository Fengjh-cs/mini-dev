"""Aggregate token counts returned by Chat Completions responses.

These are API-reported counts, never local context-size estimates. A response
without all three counts makes the corresponding total unknown.
"""

from collections import defaultdict


FIELDS = ("prompt_tokens", "completion_tokens", "total_tokens")


class ApiUsageTracker:
    def __init__(self) -> None:
        self._records: list[tuple[str, dict | None]] = []

    def record(self, kind: str, usage: object | None) -> None:
        counts = {field: getattr(usage, field, None) for field in FIELDS}
        if any(not isinstance(value, int) or value < 0 for value in counts.values()):
            self._records.append((kind, None))
        else:
            self._records.append((kind, counts))

    def summary(self) -> dict:
        by_kind: dict[str, dict] = defaultdict(lambda: {"requests": 0, "reported_requests": 0})
        totals = dict.fromkeys(FIELDS, 0)
        reported = 0
        for kind, counts in self._records:
            by_kind[kind]["requests"] += 1
            if counts is not None:
                reported += 1
                by_kind[kind]["reported_requests"] += 1
                for field in FIELDS:
                    totals[field] += counts[field]
        complete = bool(self._records) and reported == len(self._records)
        return {
            "source": "api_response_usage",
            "requests": len(self._records),
            "reported_requests": reported,
            "missing_usage_requests": len(self._records) - reported,
            "complete": complete,
            **{field: totals[field] if complete else None for field in FIELDS},
            "by_kind": dict(by_kind),
        }
