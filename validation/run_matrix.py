"""Run the fixed-model RepoMap/compaction matrix, resuming completed cases.

Each case uses run_case's independent checkout. An invalid run stops the matrix
after the current small batch so infrastructure problems do not multiply costs.
"""

import argparse
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from validation.run_case import BASELINE, CASES, agent_source_digest, run_case


VARIANTS = (
    ("map-off-compact-off", False, 0),
    ("map-on-compact-off", True, 0),
    ("map-off-compact-on", False, 2000),
    ("map-on-compact-on", True, 2000),
)


def pending_cases(root: Path, model: str,
                  resume_with_invalid: bool = False) -> list[tuple[int, Path, bool, int]]:
    pending = []
    revision = agent_source_digest()
    for label, repomap, threshold in VARIANTS:
        variant_root = root / label
        completed: set[int] = set()
        for path in variant_root.glob("*/result.json"):
            record = json.loads(path.read_text(encoding="utf-8"))
            case_id = record.get("case")
            if case_id not in CASES or case_id in completed:
                raise ValueError(f"Unknown or duplicate case in {variant_root}: {case_id}")
            status = record.get("execution_status")
            if status != "valid" and not (resume_with_invalid and status == "invalid"):
                raise ValueError(f"Invalid prior run requires review: {path}")
            if (record.get("model") != model or record.get("baseline") != BASELINE or
                    record.get("agent_source_sha256") != revision or
                    record.get("configuration") != {
                        "repomap": repomap, "compact_threshold": threshold,
                        "no_bash": True, "stream": False,
                    }):
                raise ValueError(f"Prior run has different model, baseline, Agent, or configuration: {path}")
            completed.add(case_id)
        pending.extend((case_id, variant_root, repomap, threshold)
                       for case_id in CASES if case_id not in completed)
    return pending


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--workers", type=int, default=3,
                        help="Concurrent independent cases (1-4; default 3)")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--resume-with-invalid", action="store_true",
                        help="Keep reviewed invalid runs and continue remaining cases")
    args = parser.parse_args()
    if not 1 <= args.workers <= 4:
        parser.error("workers must be 1-4")
    try:
        pending = pending_cases(args.output_root, args.model, args.resume_with_invalid)
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        parser.error(str(exc))
    print(f"{len(pending)} of {len(CASES) * len(VARIANTS)} case runs pending", flush=True)
    if args.dry_run:
        return 0
    for offset in range(0, len(pending), args.workers):
        batch = pending[offset:offset + args.workers]
        with ThreadPoolExecutor(max_workers=len(batch)) as pool:
            futures = [pool.submit(run_case, case_id, variant_root, args.model,
                                   300, 120, False, repomap, threshold)
                       for case_id, variant_root, repomap, threshold in batch]
            paths = [future.result() for future in futures]
        invalid = False
        for path in paths:
            result = json.loads(path.read_text(encoding="utf-8"))
            print(f"{path.parent.parent.name} case {result['case']}: "
                  f"{result['execution_status']}/{result['task_outcome']} "
                  f"({result['reason']}) {path}", flush=True)
            invalid |= result["execution_status"] != "valid"
        if invalid:
            print("Stopped after an invalid run; inspect artifacts before resuming.", flush=True)
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
