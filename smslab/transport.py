"""The only SMS transport in SMSLab: an in-process mock."""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass


@dataclass(frozen=True)
class DeliveryResult:
    status: str
    error_type: str | None
    latency_ms: int


class MockTransport:
    """Simulate delivery outcomes locally; this class never opens a connection."""

    def __init__(self, seed: int = 42) -> None:
        self._seed = seed

    def send(self, *, scenario: str, request_index: int, attempt: int, timeout_ms: int) -> DeliveryResult:
        material = f"{self._seed}:{request_index}:{attempt}".encode("ascii")
        latency_ms = 1 + int(hashlib.sha256(material).hexdigest()[:6], 16) % 8
        time.sleep(latency_ms / 1000.0)

        if scenario == "success":
            return DeliveryResult("delivered", None, latency_ms)
        if scenario == "transient_failure":
            if attempt == 1:
                return DeliveryResult("failed", "TransientFailure", latency_ms)
            return DeliveryResult("delivered", None, latency_ms)
        if scenario == "permanent_failure":
            return DeliveryResult("failed", "PermanentFailure", latency_ms)
        if scenario == "timeout":
            # Timeout is simulated as an outcome; the test never waits for a real timeout.
            return DeliveryResult("failed", "Timeout", timeout_ms + 1)
        if scenario == "rate_limited":
            return DeliveryResult("failed", "RateLimited", latency_ms)
        return DeliveryResult("failed", "UnsupportedScenario", latency_ms)
