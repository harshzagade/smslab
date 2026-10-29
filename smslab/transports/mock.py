"""
smslab.transports.mock — MockTransport: deterministic SMS simulation.

No network code. No real SMS is sent. All behaviour is driven by per-case scenarios
and a seeded random.Random for determinism across runs with the same seed.
"""

from __future__ import annotations

import random
import time
import uuid
from typing import Dict

from smslab.transports.base import DeliveryResult, Transport

__all__ = ["MockTransport", "SUPPORTED_SCENARIOS"]

#: Supported scenario names for SMS cases.
SUPPORTED_SCENARIOS: Dict[str, str] = {
    "success": "Message delivered; simulated latency 20-120 ms.",
    "transient_failure": "First attempt fails (TransientFailure); a single retry succeeds.",
    "permanent_failure": "Always fails with PermanentFailure (e.g. landline / DND number).",
    "timeout": "Simulated latency exceeds case timeout_ms; runner classifies as Timeout.",
    "rate_limited": "Provider returns 429 RateLimited with a retry_after_ms hint.",
    "otp_wrong_code": "OTP case scenario: first verify attempt uses a deliberately wrong code.",
}

# Real sleep cap so test runs stay fast (ms)
_MAX_REAL_SLEEP_MS = 50


class MockTransport(Transport):
    """Deterministic mock SMS transport.

    All outcomes are driven by the scenario name passed per case. The seeded
    random.Random ensures identical output for the same seed across runs.

    Attempt tracking is per-recipient (keyed by E.164 string) so that
    transient_failure retry logic works correctly.

    No network code is used. This class does not import or call socket,
    urllib, http.client, requests, or any other networking facility.
    """

    def __init__(self, seed: int = 42) -> None:
        """Initialise the mock transport with a deterministic seed.

        Args:
            seed: Integer seed for the internal random.Random instance.
        """
        self._rng = random.Random(seed)
        # Maps recipient E.164 -> attempt count for this transport instance
        self._attempts: Dict[str, int] = {}

    def reset(self) -> None:
        """Reset attempt counters (but not the RNG state)."""
        self._attempts.clear()

    def _attempt_count(self, recipient: str) -> int:
        """Return the current attempt count for a recipient (0-indexed, starts at 0)."""
        return self._attempts.get(recipient, 0)

    def _increment_attempt(self, recipient: str) -> None:
        self._attempts[recipient] = self._attempts.get(recipient, 0) + 1

    def _simulated_latency(self, lo: int = 20, hi: int = 120) -> int:
        """Draw a simulated latency value in ms from the RNG."""
        return self._rng.randint(lo, hi)

    def _message_id(self) -> str:
        """Generate a mock message ID."""
        return f"mock-{uuid.uuid4().hex[:12]}"

    def send(
        self,
        recipient: str,
        body: str,
        *,
        timeout_ms: int,
        scenario: str = "success",
    ) -> DeliveryResult:
        """Simulate an SMS send for the given scenario.

        Args:
            recipient: E.164 phone number.
            body: Message body (used for logging context, not validated here).
            timeout_ms: Case timeout threshold in milliseconds. Used by the
                        "timeout" scenario to produce a latency that exceeds it.
            scenario: One of the SUPPORTED_SCENARIOS keys.

        Returns:
            DeliveryResult describing the simulated outcome.

        Raises:
            ValueError: if scenario is not in SUPPORTED_SCENARIOS.
        """
        if scenario not in SUPPORTED_SCENARIOS:
            raise ValueError(
                f"Unknown scenario {scenario!r}. "
                f"Supported: {sorted(SUPPORTED_SCENARIOS)}"
            )

        attempt = self._attempt_count(recipient)
        self._increment_attempt(recipient)

        if scenario == "success":
            latency = self._simulated_latency(20, 120)
            _real_sleep(min(latency, _MAX_REAL_SLEEP_MS))
            return DeliveryResult(
                status="delivered",
                latency_ms=latency,
                provider_message_id=self._message_id(),
            )

        elif scenario == "transient_failure":
            if attempt == 0:
                # First attempt fails
                latency = self._simulated_latency(10, 50)
                _real_sleep(min(latency, _MAX_REAL_SLEEP_MS))
                return DeliveryResult(
                    status="failed",
                    latency_ms=latency,
                    error_type="TransientFailure",
                    error_message="Transient delivery failure; retry recommended.",
                )
            else:
                # Subsequent attempts succeed
                latency = self._simulated_latency(20, 80)
                _real_sleep(min(latency, _MAX_REAL_SLEEP_MS))
                return DeliveryResult(
                    status="delivered",
                    latency_ms=latency,
                    provider_message_id=self._message_id(),
                )

        elif scenario == "permanent_failure":
            latency = self._simulated_latency(10, 40)
            _real_sleep(min(latency, _MAX_REAL_SLEEP_MS))
            return DeliveryResult(
                status="failed",
                latency_ms=latency,
                error_type="PermanentFailure",
                error_message=(
                    "Permanent delivery failure: number may be a landline, "
                    "DND-registered, or otherwise unreachable."
                ),
            )

        elif scenario == "timeout":
            # Report a latency exceeding timeout_ms; actual real sleep is capped
            simulated_latency = timeout_ms + self._rng.randint(100, 500)
            _real_sleep(_MAX_REAL_SLEEP_MS)
            return DeliveryResult(
                status="failed",
                latency_ms=simulated_latency,
                error_type="Timeout",
                error_message=(
                    f"Simulated timeout: latency {simulated_latency} ms exceeded "
                    f"case timeout {timeout_ms} ms."
                ),
            )

        elif scenario == "rate_limited":
            retry_after = self._rng.randint(1000, 5000)
            latency = self._simulated_latency(5, 30)
            _real_sleep(min(latency, _MAX_REAL_SLEEP_MS))
            return DeliveryResult(
                status="failed",
                latency_ms=latency,
                error_type="RateLimited",
                error_message=(
                    f"Provider returned 429 Too Many Requests. "
                    f"Retry after {retry_after} ms."
                ),
                retry_after_ms=retry_after,
            )

        elif scenario == "otp_wrong_code":
            # This scenario is handled at the OTP layer (runner), not transport layer.
            # The transport itself behaves like success (message sent fine, but verify
            # will use a wrong code on the first attempt).
            latency = self._simulated_latency(20, 120)
            _real_sleep(min(latency, _MAX_REAL_SLEEP_MS))
            return DeliveryResult(
                status="delivered",
                latency_ms=latency,
                provider_message_id=self._message_id(),
            )

        # Should never reach here since we validated scenario above.
        raise ValueError(f"Unhandled scenario {scenario!r}")  # pragma: no cover


def _real_sleep(ms: int) -> None:
    """Sleep for ms milliseconds (non-blocking, capped implementation detail)."""
    if ms > 0:
        time.sleep(ms / 1000.0)
