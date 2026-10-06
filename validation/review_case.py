"""Record a human verdict for a manual real-task case."""

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from validation.run_case import CASES


def record_review(path: Path, verdict: str, notes: str) -> dict:
    result = json.loads(path.read_text(encoding="utf-8"))
    case_id = result.get("case")
    if case_id not in CASES or CASES[case_id]["grading"] != "manual":
        raise ValueError("Only manual cases can receive a human verdict")
    if result.get("execution_status") != "valid" or result.get("task_outcome") != "needs_review":
        raise ValueError("Review requires a valid run awaiting review")
    if verdict not in ("passed", "failed") or not notes.strip():
        raise ValueError("A passed/failed verdict and review notes are required")
    result["task_outcome"] = verdict
    result["reason"] = "human_review"
    result["review"] = {
        "verdict": verdict,
        "notes": notes.strip(),
        "reviewed_at_utc": datetime.now(timezone.utc).isoformat(),
    }
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("result", type=Path, help="Path to the case result.json")
    parser.add_argument("--verdict", choices=("passed", "failed"), required=True)
    parser.add_argument("--notes", required=True, help="Concrete evidence for the verdict")
    args = parser.parse_args()
    try:
        result = record_review(args.result, args.verdict, args.notes)
    except ValueError as exc:
        parser.error(str(exc))
    print(f"case {result['case']}: manual {result['task_outcome']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
