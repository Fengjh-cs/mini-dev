"""Compare paired real-task runs with one fixed model and Agent revision.

Usage totals come only from API response usage. Trace context estimates are
reported in a separate field and are never summed as billed tokens.
"""

import argparse
import json
from pathlib import Path

from validation.run_case import CASES
from validation.summary import summarize


def load_variant(root: Path) -> dict[int, dict]:
    records: dict[int, dict] = {}
    for path in sorted(root.glob("*/result.json")):
        record = json.loads(path.read_text(encoding="utf-8"))
        if record.get("execution_status") == "prepared":
            continue
        case_id = record.get("case")
        if case_id not in CASES or case_id in records:
            raise ValueError(f"Unknown or duplicate case {case_id} in {root}")
        records[case_id] = record
    if not records:
        raise ValueError(f"No completed result.json files in {root}")
    return records


def _actual_usage(records: list[dict]) -> dict:
    fields = ("prompt_tokens", "completion_tokens", "total_tokens")
    complete = [r["api_usage"] for r in records
                if r.get("execution_status") == "valid"
                and isinstance(r.get("api_usage"), dict) and r["api_usage"].get("complete")]
    covered = len(complete)
    return {
        "source": "api_response_usage",
        "complete_runs": covered,
        "runs": len(records),
        "requests": sum(u["requests"] for u in complete) if covered == len(records) else None,
        **{field: sum(u[field] for u in complete) if covered == len(records) else None
           for field in fields},
    }


def _estimated_context(records: list[dict]) -> dict:
    estimates = [r["context_estimate"] for r in records
                 if isinstance(r.get("context_estimate"), dict)]
    peaks = [e["peak_observed_context_tokens"] for e in estimates
             if e.get("peak_observed_context_tokens") is not None]
    return {
        "source": "trace_character_count_divided_by_four",
        "runs_with_observed_peak": len(peaks),
        "runs": len(records),
        "mean_observed_peak_context_tokens": sum(peaks) / len(peaks) if peaks else None,
        "trace_compaction_attempts": sum(e.get("compaction_events", 0) for e in estimates),
    }


def _paired_usage(variants: dict[str, dict[int, dict]], ids: set[int]) -> dict:
    common = sorted(i for i in ids if all(
        variants[label][i].get("execution_status") == "valid"
        and isinstance(variants[label][i].get("api_usage"), dict)
        and variants[label][i]["api_usage"].get("complete")
        for label in variants))
    labels = list(variants)
    by_variant = {}
    for label, records in variants.items():
        usage = [records[i]["api_usage"] for i in common]
        by_variant[label] = {
            "requests": sum(u["requests"] for u in usage),
            "compaction_summary_requests": sum(
                u.get("by_kind", {}).get("compaction", {}).get("requests", 0)
                for u in usage
            ),
            "prompt_tokens": sum(u["prompt_tokens"] for u in usage),
            "completion_tokens": sum(u["completion_tokens"] for u in usage),
            "total_tokens": sum(u["total_tokens"] for u in usage),
        }
    baseline = by_variant[labels[0]]["total_tokens"]
    for label in labels:
        total = by_variant[label]["total_tokens"]
        by_variant[label]["total_tokens_change_vs_first_pct"] = (
            (total - baseline) / baseline * 100 if baseline else None
        )
    return {"source": "api_response_usage", "case_ids": common,
            "coverage": f"{len(common)}/{len(ids)}", "variants": by_variant}


def compare(variants: dict[str, dict[int, dict]]) -> dict:
    if len(variants) < 2:
        raise ValueError("At least two variants are required")
    labels = list(variants)
    ids = set(variants[labels[0]])
    if not ids:
        raise ValueError("Variants contain no completed cases")
    if any(set(records) != ids for records in variants.values()):
        raise ValueError("Variants must contain exactly the same case IDs")
    fixed_fields = ("baseline", "model", "api_type", "api_endpoint_host", "agent_source_sha256")
    reference = variants[labels[0]]
    first = reference[next(iter(ids))]
    if any(any(record.get(field) is None or record.get(field) != first.get(field)
               for field in fixed_fields)
           for record in reference.values()):
        raise ValueError("Reference runs must use one model, endpoint, baseline, and Agent revision")
    reference_config = first.get("configuration")
    configurations_seen: set[str] = set()
    for label, records in variants.items():
        configurations = {json.dumps(r.get("configuration"), sort_keys=True)
                          for r in records.values()}
        if len(configurations) != 1 or any(r.get("configuration") is None
                                            for r in records.values()):
            raise ValueError(f"Variant {label} mixes or omits configurations")
        config = next(iter(records.values()))["configuration"]
        if set(config) != {"repomap", "compact_threshold", "no_bash", "stream"}:
            raise ValueError(f"Variant {label} has unknown or missing configuration fields")
        if any(config.get(key) != reference_config.get(key)
               for key in ("no_bash", "stream")):
            raise ValueError(f"Variant {label} changes settings beyond RepoMap and compaction")
        fingerprint = next(iter(configurations))
        if fingerprint in configurations_seen:
            raise ValueError(f"Variant {label} repeats another configuration")
        configurations_seen.add(fingerprint)
        for case_id in ids:
            record, original = records[case_id], reference[case_id]
            if record.get("grading") != CASES[case_id]["grading"]:
                raise ValueError(f"Grading mismatch in {label}, case {case_id}")
            if any(record.get(field) is None or record.get(field) != original.get(field)
                   for field in fixed_fields) or record.get("prompt") != original.get("prompt"):
                raise ValueError(f"Model, endpoint, baseline, Agent, or prompt mismatch in {label}, case {case_id}")
    output = {
        "case_ids": sorted(ids),
        "fixed": {field: reference[next(iter(ids))][field] for field in fixed_fields},
        "variants": {},
        "paired_automatic_vs_first": {},
        "paired_actual_api_usage": {
            "all_cases": _paired_usage(variants, ids),
            "automatic_cases": _paired_usage(
                variants, {i for i in ids if CASES[i]["grading"] == "automatic"}
            ),
        },
    }
    for label, records in variants.items():
        ordered = [records[i] for i in sorted(ids)]
        output["variants"][label] = {
            "configuration": ordered[0]["configuration"],
            "functional": summarize(ordered),
            "actual_api_usage": _actual_usage(ordered),
            "estimated_context": _estimated_context(ordered),
        }
    for label in labels[1:]:
        pairs = [(reference[i], variants[label][i]) for i in sorted(ids)
                 if CASES[i]["grading"] == "automatic"
                 and reference[i].get("execution_status") == "valid"
                 and variants[label][i].get("execution_status") == "valid"]
        output["paired_automatic_vs_first"][label] = {
            "paired_valid_cases": len(pairs),
            "improved": sum(a["task_outcome"] == "failed" and b["task_outcome"] == "passed"
                            for a, b in pairs),
            "regressed": sum(a["task_outcome"] == "passed" and b["task_outcome"] == "failed"
                             for a, b in pairs),
            "both_passed": sum(a["task_outcome"] == b["task_outcome"] == "passed"
                               for a, b in pairs),
            "both_failed": sum(a["task_outcome"] == b["task_outcome"] == "failed"
                               for a, b in pairs),
        }
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--variant", nargs=2, action="append", metavar=("LABEL", "RESULT_DIR"),
                        required=True, help="Repeat for each configuration; first is reference")
    parser.add_argument("--output", type=Path, help="Also save the comparison JSON here")
    args = parser.parse_args()
    labels = [label for label, _ in args.variant]
    if len(labels) != len(set(labels)):
        parser.error("Variant labels must be unique")
    try:
        report = compare({label: load_variant(Path(root)) for label, root in args.variant})
    except (ValueError, KeyError, TypeError) as exc:
        parser.error(str(exc))
    rendered = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
