"""
smslab.report — Report serialization and text rendering.

Converts a Report dataclass to a JSON-serialisable dict and produces a human-readable
text summary for CLI output.
"""

from __future__ import annotations

import json
from typing import Any, Dict

from smslab.runner import Report

__all__ = ["report_to_dict", "report_to_json", "render_text_summary"]


def report_to_dict(report: Report) -> Dict[str, Any]:
    """Convert a Report to a JSON-serialisable dictionary.

    Args:
        report: The Report produced by run_cases().

    Returns:
        A dict with all report fields, safe for json.dumps().
    """
    results_list = []
    for r in report.results:
        entry: Dict[str, Any] = {
            "name": r.name,
            "kind": r.kind,
            "recipient": r.recipient,
            "scenario": r.scenario,
            "expected": r.expected,
            "actual_status": r.actual_status,
            "outcome": r.outcome,
            "attempts": r.attempts,
            "latency_ms": r.latency_ms,
        }
        if r.error_type is not None:
            entry["error_type"] = r.error_type
        if r.error_message is not None:
            entry["error_message"] = r.error_message
        if r.retry_after_ms is not None:
            entry["retry_after_ms"] = r.retry_after_ms
        results_list.append(entry)

    return {
        "smslab_version": "1.0.0",
        "started_at": report.started_at,
        "seed": report.seed,
        "transport": report.transport,
        "summary": {
            "total": report.summary.total,
            "passed": report.summary.passed,
            "failed": report.summary.failed,
            "delivered": report.summary.delivered,
            "errors_by_type": report.summary.errors_by_type,
            "duration_ms": report.summary.duration_ms,
            "throughput_per_s": report.summary.throughput_per_s,
        },
        "results": results_list,
    }


def report_to_json(report: Report, indent: int = 2) -> str:
    """Serialise a Report to a JSON string.

    Args:
        report: The Report produced by run_cases().
        indent: JSON indentation level (default 2).

    Returns:
        Indented JSON string.
    """
    return json.dumps(report_to_dict(report), indent=indent)


def render_text_summary(report: Report) -> str:
    """Render a human-readable text summary of a report.

    Args:
        report: The Report produced by run_cases().

    Returns:
        Multi-line string suitable for console output.
    """
    s = report.summary
    lines = [
        "",
        "=" * 70,
        "  SMSLab Run Report",
        "=" * 70,
        f"  Started:    {report.started_at}",
        f"  Transport:  {report.transport}",
        f"  Seed:       {report.seed}",
        f"  Duration:   {s.duration_ms} ms  ({s.throughput_per_s:.2f} cases/s)",
        "-" * 70,
        f"  Total:      {s.total}",
        f"  Passed:     {s.passed}",
        f"  Failed:     {s.failed}",
        f"  Delivered:  {s.delivered}",
    ]

    if s.errors_by_type:
        lines.append("  Errors by type:")
        for err_type, count in sorted(s.errors_by_type.items()):
            lines.append(f"    {err_type:<22s} {count}")

    lines.append("-" * 70)
    lines.append("  Case Results:")
    lines.append("")

    for r in report.results:
        icon = "✓" if r.outcome == "pass" else "✗"
        status_col = f"{r.actual_status:<12s}"
        err_col = f" [{r.error_type}]" if r.error_type else ""
        retry_col = f" retry_after={r.retry_after_ms}ms" if r.retry_after_ms else ""
        lines.append(
            f"  {icon} {r.kind:3s}  {r.name:<32s}"
            f"  {status_col} (expected: {r.expected:<10s})"
            f"  {r.latency_ms:5d}ms  attempts={r.attempts}"
            f"{err_col}{retry_col}"
        )

    lines.append("")
    lines.append("=" * 70)

    all_pass = s.passed == s.total
    verdict = "ALL CASES PASSED" if all_pass else f"{s.failed} CASE(S) FAILED"
    lines.append(f"  {verdict}")
    lines.append("=" * 70)
    lines.append("")

    return "\n".join(lines)
