"""Concurrent scenario runner and JSON reporting."""
from __future__ import annotations
import json
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from smslab.otp import OtpService
from smslab.transport import MockTransport


def _wrong_code(code):
    return ("1" if code[0] != "1" else "2") + code[1:]


def run_cases(config, cases=None, concurrency=None):
    selected = tuple(config.cases if cases is None else cases)
    if not selected:
        raise ValueError("At least one case is required.")
    if len(selected) > config.limits.max_requests:
        raise ValueError("Request count exceeds the configured hard cap.")
    workers = config.limits.concurrency if concurrency is None else concurrency
    if isinstance(workers, bool) or not isinstance(workers, int) or not 1 <= workers <= config.limits.concurrency:
        raise ValueError("Concurrency exceeds the configured safety cap.")
    start_wall = time.perf_counter()
    started_at = datetime.now(timezone.utc).isoformat()
    transport = MockTransport(config.seed)

    def run_one(index, case):
        started = time.perf_counter()
        error_type, attempts = None, 1
        if case.kind == "sms":
            first = transport.send(scenario=case.scenario, request_index=index, attempt=1, timeout_ms=config.limits.timeout_ms)
            result = first
            if case.scenario == "transient_failure" and first.error_type == "TransientFailure":
                attempts = 2
                result = transport.send(scenario=case.scenario, request_index=index, attempt=2, timeout_ms=config.limits.timeout_ms)
            actual, error_type = result.status, result.error_type
            latency = first.latency_ms + (result.latency_ms if attempts == 2 else 0)
        else:
            now = [1000.0]
            otp = OtpService(ttl_seconds=300, max_attempts=3, clock=lambda: now[0])
            code = otp.issue(case.recipient)
            if case.scenario == "success":
                actual, latency = otp.verify(case.recipient, code), 0
            elif case.scenario == "wrong_code":
                actual, latency, error_type = otp.verify(case.recipient, _wrong_code(code)), 0, "WrongCode"
            elif case.scenario == "expired":
                now[0] += 301
                actual, latency, error_type = otp.verify(case.recipient, code), 0, "Expired"
            else:
                for _ in range(3):
                    actual = otp.verify(case.recipient, _wrong_code(code))
                latency, error_type = 0, "Locked"
        elapsed = int((time.perf_counter() - started) * 1000)
        item = {"name": case.name, "kind": case.kind, "recipient": case.recipient,
                "scenario": case.scenario, "expected": case.expected, "actual": actual,
                "outcome": "pass" if actual == case.expected else "fail", "attempts": attempts,
                "latency_ms": max(latency, elapsed)}
        if error_type:
            item["error_type"] = error_type
        return item

    results = [None] * len(selected)
    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="smslab-mock") as pool:
        futures = {pool.submit(run_one, i, case): i for i, case in enumerate(selected)}
        for future in as_completed(futures):
            results[futures[future]] = future.result()
    complete = [item for item in results if item is not None]
    duration = max(1, int((time.perf_counter() - start_wall) * 1000))
    passed = sum(item["outcome"] == "pass" for item in complete)
    errors = Counter(item["error_type"] for item in complete if item.get("error_type"))
    summary = {"total": len(complete), "passed": passed, "failed": len(complete) - passed,
               "delivered": sum(item["actual"] == "delivered" for item in complete),
               "errors_by_type": dict(sorted(errors.items())), "duration_ms": duration,
               "throughput_per_s": round(len(complete) / (duration / 1000), 3)}
    return {"schema_version": 1, "started_at": started_at, "transport": "mock",
            "seed": config.seed, "concurrency": workers, "summary": summary, "results": complete}


def write_report(report, path):
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(target.name + ".tmp")
    temporary.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(target)
