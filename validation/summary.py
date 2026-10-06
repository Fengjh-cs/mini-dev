"""Summarize real-task results without mixing automatic and manual verdicts."""

import argparse
import json
import tempfile
from pathlib import Path

from validation.run_case import CASES


def summarize(records: list[dict]) -> dict:
    by_case: dict[int, dict] = {}
    attempted: set[int] = set()
    invalid_runs = {"automatic": 0, "manual": 0}
    for record in records:
        if record.get("execution_status") == "prepared":
            continue
        case_id = record.get("case")
        if case_id not in CASES or record.get("grading") != CASES[case_id]["grading"]:
            raise ValueError(f"Unknown case or grading mismatch: {case_id}")
        attempted.add(case_id)
        grading = CASES[case_id]["grading"]
        status = record.get("execution_status")
        if status == "invalid":
            invalid_runs[grading] += 1
            continue
        if status != "valid":
            raise ValueError(f"Unknown execution status for case {case_id}: {status}")
        if case_id in by_case:
            raise ValueError(f"Case {case_id} has multiple valid runs; select one before reporting")
        outcome = record.get("task_outcome")
        allowed = {"passed", "failed"} if grading == "automatic" else {
            "passed", "failed", "needs_review"}
        if outcome not in allowed:
            raise ValueError(f"Invalid outcome for case {case_id}: {outcome}")
        if grading == "manual" and (outcome == "passed" or
                                    record.get("reason") == "human_review"):
            review = record.get("review", {})
            if review.get("verdict") != outcome or not review.get("notes", "").strip():
                raise ValueError(f"Case {case_id} needs recorded human review evidence")
        by_case[case_id] = record

    automatic = [r for i, r in by_case.items() if CASES[i]["grading"] == "automatic"]
    manual = [r for i, r in by_case.items() if CASES[i]["grading"] == "manual"]
    auto_passed = sum(r["task_outcome"] == "passed" for r in automatic)
    auto_failed = sum(r["task_outcome"] == "failed" for r in automatic)
    return {
        "catalog": {"total": len(CASES),
                    "automatic": sum(c["grading"] == "automatic" for c in CASES.values()),
                    "manual": sum(c["grading"] == "manual" for c in CASES.values())},
        "automatic": {
            "passed": auto_passed,
            "failed": auto_failed,
            "valid": len(automatic),
            "invalid_runs": invalid_runs["automatic"],
            "not_run": sum(c["grading"] == "automatic" and i not in attempted
                           for i, c in CASES.items()),
            "success_rate": auto_passed / len(automatic) if automatic else None,
        },
        "manual": {
            "passed_after_review": sum(r["task_outcome"] == "passed" for r in manual),
            "failed_after_review": sum(r["task_outcome"] == "failed" and
                                       r.get("reason") == "human_review" for r in manual),
            "failed_precheck": sum(r["task_outcome"] == "failed" and
                                   r.get("reason") != "human_review" for r in manual),
            "needs_review": sum(r["task_outcome"] == "needs_review" for r in manual),
            "invalid_runs": invalid_runs["manual"],
            "not_run": sum(c["grading"] == "manual" and i not in attempted
                           for i, c in CASES.items()),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", type=Path,
                        default=Path(tempfile.gettempdir()) / "mindev-validation")
    args = parser.parse_args()
    records = [json.loads(path.read_text(encoding="utf-8"))
               for path in args.output_root.glob("*/result.json")]
    try:
        result = summarize(records)
    except ValueError as exc:
        parser.error(str(exc))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
