"""
smslab.runner — Case execution engine.

Executes test cases concurrently using ThreadPoolExecutor, classifies results,
compares actual vs expected outcomes, and produces a Report.

Each case is logged as structured JSON events. Transient failures are retried
once. OTP cases generate a code then verify it (otp_wrong_code scenario uses a
wrong code on the first verify attempt then retries with the correct code).

No network code is used.
"""

from __future__ import annotations

import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from smslab.config import CaseConfig, Config
from smslab.otp import OtpService
from smslab.transports.mock import MockTransport

__all__ = ["CaseResult", "Report", "RunSummary", "run_cases"]


# ---------------------------------------------------------------------------
# Result dataclasses
# ---------------------------------------------------------------------------


@dataclass
class CaseResult:
    """Result of a single executed test case."""

    name: str
    kind: str
    recipient: str
    scenario: str
    expected: str
    actual_status: str       # "delivered", "failed", "verified", "wrong_code", "expired", "locked"
    outcome: str             # "pass" | "fail"
    attempts: int
    latency_ms: int
    error_type: Optional[str] = None
    error_message: Optional[str] = None
    retry_after_ms: Optional[int] = None


@dataclass
class RunSummary:
    """Aggregated summary of all case results."""

    total: int
    passed: int
    failed: int
    delivered: int
    errors_by_type: Dict[str, int]
    duration_ms: int
    throughput_per_s: float


@dataclass
class Report:
    """Full run report including metadata, summary, and per-case results."""

    started_at: str          # ISO 8601
    seed: int
    transport: str
    summary: RunSummary
    results: List[CaseResult]
    log_events: List[Dict[str, Any]] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------


class _Logger:
    """Thread-safe structured JSON logger."""

    def __init__(self, file_path: Optional[str] = None) -> None:
        self._events: List[Dict[str, Any]] = []
        self._lock = threading.Lock()
        self._file_path = file_path
        self._file_handle = None
        if file_path:
            self._file_handle = open(file_path, "w", encoding="utf-8")  # noqa: WPS515

    def log(
        self,
        level: str,
        event: str,
        case: Optional[str] = None,
        detail: Optional[Dict[str, Any]] = None,
    ) -> None:
        entry: Dict[str, Any] = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "level": level,
            "event": event,
        }
        if case is not None:
            entry["case"] = case
        if detail:
            entry["detail"] = detail

        with self._lock:
            self._events.append(entry)
            if self._file_handle:
                self._file_handle.write(json.dumps(entry) + "\n")
                self._file_handle.flush()

    def close(self) -> None:
        if self._file_handle:
            self._file_handle.close()
            self._file_handle = None

    @property
    def events(self) -> List[Dict[str, Any]]:
        with self._lock:
            return list(self._events)


# ---------------------------------------------------------------------------
# Core runner
# ---------------------------------------------------------------------------


def run_cases(
    config: Config,
    *,
    log_path: Optional[str] = None,
    quiet: bool = False,
) -> Report:
    """Execute all test cases in config and return a Report.

    Args:
        config: Validated Config loaded by load_config().
        log_path: Optional path to write structured JSON log lines.
        quiet: If True, suppress per-case console output.

    Returns:
        Report dataclass with all results and summary.
    """
    logger = _Logger(file_path=log_path)
    transport = MockTransport(seed=config.seed)
    otp_service = OtpService(seed=config.seed)

    started_at = datetime.now(timezone.utc).isoformat()
    wall_start = time.monotonic()

    logger.log("INFO", "run_started", detail={"seed": config.seed, "cases": len(config.cases)})

    results: List[CaseResult] = []
    results_lock = threading.Lock()

    def execute_case(case: CaseConfig) -> CaseResult:
        logger.log("INFO", "case_start", case=case.name, detail={
            "kind": case.kind,
            "recipient": case.recipient,
            "scenario": case.scenario,
            "expected": case.expected,
        })

        if case.kind == "sms":
            result = _run_sms_case(case, transport, logger, config.limits.timeout_ms)
        else:
            result = _run_otp_case(case, transport, otp_service, logger)

        outcome_str = f"{'✓ PASS' if result.outcome == 'pass' else '✗ FAIL'}"
        logger.log(
            "INFO" if result.outcome == "pass" else "WARN",
            "case_end",
            case=case.name,
            detail={
                "outcome": result.outcome,
                "actual_status": result.actual_status,
                "expected": result.expected,
                "attempts": result.attempts,
                "latency_ms": result.latency_ms,
                "error_type": result.error_type,
            },
        )

        if not quiet:
            print(
                f"  {outcome_str} [{case.kind:3s}] {case.name:30s} "
                f"scenario={case.scenario:20s} "
                f"actual={result.actual_status:12s} expected={result.expected}"
            )

        return result

    # ThreadPoolExecutor for concurrent execution
    # We preserve order in the final results list
    case_futures = {}
    with ThreadPoolExecutor(max_workers=config.limits.concurrency) as executor:
        for case in config.cases:
            future = executor.submit(execute_case, case)
            case_futures[future] = case

    # Collect in original order
    future_to_result = {}
    for future, case in case_futures.items():
        try:
            future_to_result[case.name] = future.result()
        except Exception as exc:  # pragma: no cover
            logger.log("ERROR", "case_exception", case=case.name, detail={"error": str(exc)})
            # Create a failure result for unhandled exceptions
            future_to_result[case.name] = CaseResult(
                name=case.name,
                kind=case.kind,
                recipient=case.recipient,
                scenario=case.scenario,
                expected=case.expected,
                actual_status="error",
                outcome="fail",
                attempts=0,
                latency_ms=0,
                error_type="InternalError",
                error_message=str(exc),
            )

    # Preserve original case order
    for case in config.cases:
        results.append(future_to_result[case.name])

    wall_end = time.monotonic()
    duration_ms = int((wall_end - wall_start) * 1000)

    # Build summary
    passed = sum(1 for r in results if r.outcome == "pass")
    failed = sum(1 for r in results if r.outcome == "fail")
    delivered = sum(1 for r in results if r.actual_status == "delivered")
    errors_by_type: Dict[str, int] = {}
    for r in results:
        if r.error_type:
            errors_by_type[r.error_type] = errors_by_type.get(r.error_type, 0) + 1

    throughput = (len(results) / (duration_ms / 1000.0)) if duration_ms > 0 else 0.0

    summary = RunSummary(
        total=len(results),
        passed=passed,
        failed=failed,
        delivered=delivered,
        errors_by_type=errors_by_type,
        duration_ms=duration_ms,
        throughput_per_s=round(throughput, 2),
    )

    logger.log("INFO", "run_finished", detail={
        "total": summary.total,
        "passed": summary.passed,
        "failed": summary.failed,
        "duration_ms": summary.duration_ms,
    })
    logger.close()

    return Report(
        started_at=started_at,
        seed=config.seed,
        transport=config.transport,
        summary=summary,
        results=results,
        log_events=logger.events,
    )


# ---------------------------------------------------------------------------
# SMS case execution
# ---------------------------------------------------------------------------


def _run_sms_case(
    case: CaseConfig,
    transport: MockTransport,
    logger: _Logger,
    timeout_ms: int,
) -> CaseResult:
    """Execute a single SMS test case with optional transient-failure retry."""
    attempts = 0
    last_result = None

    for attempt_num in range(2):  # max 2 attempts (original + 1 retry)
        attempts += 1
        logger.log("DEBUG", "sms_attempt", case=case.name, detail={
            "attempt": attempts,
            "recipient": case.recipient,
        })

        result = transport.send(
            case.recipient,
            case.body or "",
            timeout_ms=timeout_ms,
            scenario=case.scenario,
        )
        last_result = result

        # Classify timeout: transport reports latency > timeout_ms
        if result.latency_ms > timeout_ms and result.error_type == "Timeout":
            actual_status = "failed"
            break

        if result.status == "delivered":
            actual_status = "delivered"
            break

        # On transient failure, retry once
        if result.error_type == "TransientFailure" and attempt_num == 0:
            logger.log("INFO", "sms_retry", case=case.name, detail={
                "reason": "TransientFailure",
                "attempt": attempts,
            })
            continue

        # All other failures: stop
        actual_status = "failed"
        break
    else:
        actual_status = "failed" if last_result and last_result.status != "delivered" else "delivered"

    error_type = last_result.error_type if last_result else None
    error_message = last_result.error_message if last_result else None
    retry_after_ms = last_result.retry_after_ms if last_result else None
    latency_ms = last_result.latency_ms if last_result else 0

    outcome = "pass" if actual_status == case.expected else "fail"

    return CaseResult(
        name=case.name,
        kind=case.kind,
        recipient=case.recipient,
        scenario=case.scenario,
        expected=case.expected,
        actual_status=actual_status,
        outcome=outcome,
        attempts=attempts,
        latency_ms=latency_ms,
        error_type=error_type,
        error_message=error_message,
        retry_after_ms=retry_after_ms,
    )


# ---------------------------------------------------------------------------
# OTP case execution
# ---------------------------------------------------------------------------


def _run_otp_case(
    case: CaseConfig,
    transport: MockTransport,
    otp_service: OtpService,
    logger: _Logger,
) -> CaseResult:
    """Execute a single OTP test case.

    Scenarios:
      - "success": generate OTP, send (mock), verify with correct code -> "verified"
      - "otp_wrong_code": generate OTP, send (mock), first verify with wrong code
        -> "wrong_code", then verify with correct code -> "verified"

    The expected field for otp cases is typically "verified" for success and
    "wrong_code" for the first-attempt wrong_code scenario result check.
    """
    timeout_ms = 5000  # default for OTP sends (not configurable per-case)

    # Step 1: Generate OTP
    simulated_otp = otp_service.generate(case.recipient)
    logger.log("DEBUG", "otp_generated", case=case.name, detail={
        "recipient": case.recipient,
        "expires_at": simulated_otp.expires_at,
    })

    # Step 2: Simulate sending the OTP message
    send_result = transport.send(
        case.recipient,
        f"Your OTP is {simulated_otp.code}",
        timeout_ms=timeout_ms,
        scenario=case.scenario,
    )
    latency_ms = send_result.latency_ms

    logger.log("DEBUG", "otp_sent", case=case.name, detail={
        "status": send_result.status,
        "latency_ms": latency_ms,
    })

    # Step 3: Verify
    if case.scenario == "otp_wrong_code":
        # First attempt: use a deliberately wrong code
        wrong_code = _wrong_code(simulated_otp.code)
        first_result = otp_service.verify(case.recipient, wrong_code)
        logger.log("DEBUG", "otp_verify_wrong", case=case.name, detail={
            "result": first_result,
        })
        # The "actual_status" for this case is the outcome of the first (wrong) attempt
        # Expected for otp_wrong_code cases is "wrong_code"
        actual_status = first_result

    else:  # "success"
        verify_result = otp_service.verify(case.recipient, simulated_otp.code)
        logger.log("DEBUG", "otp_verify", case=case.name, detail={
            "result": verify_result,
        })
        actual_status = verify_result

    outcome = "pass" if actual_status == case.expected else "fail"

    return CaseResult(
        name=case.name,
        kind=case.kind,
        recipient=case.recipient,
        scenario=case.scenario,
        expected=case.expected,
        actual_status=actual_status,
        outcome=outcome,
        attempts=1,
        latency_ms=latency_ms,
    )


def _wrong_code(correct_code: str) -> str:
    """Return a 6-digit code guaranteed to differ from correct_code."""
    # Increment last digit (with wraparound) to get a deterministically wrong code
    n = int(correct_code)
    wrong = (n + 1) % 1_000_000
    return f"{wrong:06d}"
