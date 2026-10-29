"""Bounded, in-process burst simulation for rate-limit testing.

This module has no messaging transport and never contacts a phone number.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

MAX_BURST_ATTEMPTS = 100
MAX_ACCEPTED_PER_WINDOW = 10
MAX_WINDOW_SECONDS = 3600


def simulate_burst(
    attempts: int = 10,
    limit: int = 2,
    window_seconds: int = 60,
) -> dict:
    """Simulate simultaneous requests against a simple fixed-window limiter."""
    for name, value, minimum, maximum in (
        ("attempts", attempts, 1, MAX_BURST_ATTEMPTS),
        ("limit", limit, 1, MAX_ACCEPTED_PER_WINDOW),
        ("window_seconds", window_seconds, 1, MAX_WINDOW_SECONDS),
    ):
        if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
            raise ValueError(f"{name} must be an integer between {minimum} and {maximum}.")
    if limit > attempts:
        raise ValueError("limit cannot exceed attempts.")

    results = []
    for index in range(1, attempts + 1):
        accepted = index <= limit
        results.append({
            "request_id": index,
            "recipient": "synthetic-test-recipient",
            "outcome": "accepted_by_mock_limiter" if accepted else "rejected_rate_limit",
            "sms_sent": False,
        })

    return {
        "schema_version": 1,
        "simulation": "mock-burst",
        "started_at": datetime.now(timezone.utc).isoformat(),
        "transport": "none",
        "actual_transmissions": 0,
        "window_seconds": window_seconds,
        "summary": {
            "attempted": attempts,
            "accepted_by_mock_limiter": limit,
            "rejected_rate_limit": attempts - limit,
        },
        "results": results,
    }


def write_burst_report(report: dict, path: str | Path) -> None:
    """Write a deterministic-schema JSON report atomically."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(target.name + ".tmp")
    temporary.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(target)
