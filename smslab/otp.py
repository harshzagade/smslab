"""
smslab.otp — Simulated OTP generation and verification.

This is a LOCAL SIMULATION for developers testing their own OTP integration logic.
No real OTP is sent anywhere. The generated codes exist only in memory and are
stored exclusively as SHA-256 hashes — the plaintext code is returned once at
generation time and is never stored.

No network code is used in this module.
"""

from __future__ import annotations

import hashlib
import random
import time
from dataclasses import dataclass
from typing import Dict, Optional, Tuple

__all__ = ["OtpService", "SimulatedOtp"]

_MAX_ATTEMPTS = 3
_DEFAULT_EXPIRY_SECONDS = 300  # 5 minutes


@dataclass
class SimulatedOtp:
    """A simulated OTP code returned to the developer for verification testing.

    The code is a 6-digit string (e.g. "047821"). This is a LOCAL SIMULATION —
    the code has no real-world validity. It is returned from OtpService.generate()
    so the developer can drive their own verify() call with it.

    Attributes:
        recipient: E.164 phone number the OTP is associated with.
        code: 6-digit plaintext OTP code (only available at generation time).
        expires_at: Unix timestamp (seconds) after which the OTP is expired.
    """

    recipient: str
    code: str
    expires_at: float

    def __repr__(self) -> str:
        return (
            f"SimulatedOtp(recipient={self.recipient!r}, "
            f"code='<SIMULATED:{self.code}>', "
            f"expires_at={self.expires_at})"
        )


# Stored OTP record (internal to OtpService)
# (hash, expires_at, wrong_attempt_count)
_OtpRecord = Tuple[str, float, int]


def _sha256_hex(code: str) -> str:
    """Return the SHA-256 hex digest of the OTP code."""
    return hashlib.sha256(code.encode()).hexdigest()


class OtpService:
    """Local OTP simulation service.

    Generates 6-digit codes from a seeded RNG, stores only their SHA-256 hash
    with an expiry timestamp and attempt counter. Supports injectable time for
    deterministic tests.

    No network code. Nothing is sent anywhere.
    """

    def __init__(
        self,
        seed: int = 42,
        expiry_seconds: int = _DEFAULT_EXPIRY_SECONDS,
        clock_offset_seconds: float = 0.0,
    ) -> None:
        """Initialise the OTP service.

        Args:
            seed: RNG seed for reproducible code generation.
            expiry_seconds: How long codes are valid (default 300s / 5 min).
            clock_offset_seconds: Added to time.time() for simulated time tests.
        """
        self._rng = random.Random(seed)
        self._expiry_seconds = expiry_seconds
        self._clock_offset = clock_offset_seconds
        # Maps recipient E.164 -> (hash, expires_at, attempt_count)
        self._store: Dict[str, _OtpRecord] = {}

    def _now(self, now: Optional[float] = None) -> float:
        """Return current time, supporting injection and clock offset."""
        base = now if now is not None else time.time()
        return base + self._clock_offset

    def generate(self, recipient: str, *, now: Optional[float] = None) -> SimulatedOtp:
        """Generate a simulated 6-digit OTP for the recipient.

        Stores only the SHA-256 hash of the code. Any previously generated OTP
        for this recipient is overwritten (e.g. resend scenario).

        Args:
            recipient: E.164 phone number.
            now: Optional current time (seconds since epoch) for testing.

        Returns:
            SimulatedOtp with the plaintext code and expiry time.
        """
        code = f"{self._rng.randint(0, 999999):06d}"
        current_time = self._now(now)
        expires_at = current_time + self._expiry_seconds
        self._store[recipient] = (_sha256_hex(code), expires_at, 0)
        return SimulatedOtp(recipient=recipient, code=code, expires_at=expires_at)

    def verify(
        self, recipient: str, code: str, *, now: Optional[float] = None
    ) -> str:
        """Verify an OTP code for the recipient.

        Args:
            recipient: E.164 phone number.
            code: Code to verify (plaintext 6-digit string).
            now: Optional current time for testing.

        Returns:
            One of:
              "verified"  — code is correct and not expired
              "wrong_code" — code is incorrect (and lockout not yet triggered)
              "expired"   — code was correct hash but past expiry time
              "locked"    — too many wrong attempts (>= 3); no more tries allowed
              "not_found" — no OTP has been generated for this recipient
        """
        if recipient not in self._store:
            return "not_found"

        stored_hash, expires_at, attempt_count = self._store[recipient]

        # Locked check (done before time check — lockout persists)
        if attempt_count >= _MAX_ATTEMPTS:
            return "locked"

        current_time = self._now(now)

        # Check expiry
        if current_time > expires_at:
            return "expired"

        # Validate code
        if _sha256_hex(code) != stored_hash:
            # Increment attempt count
            self._store[recipient] = (stored_hash, expires_at, attempt_count + 1)
            # If this wrong attempt pushed us to the limit, next call returns "locked"
            return "wrong_code"

        # Correct — consume the OTP (remove it so it can't be reused)
        del self._store[recipient]
        return "verified"

    def invalidate(self, recipient: str) -> None:
        """Manually invalidate any stored OTP for the recipient."""
        self._store.pop(recipient, None)

    def has_pending(self, recipient: str) -> bool:
        """Return True if there is a non-expired, non-locked OTP for recipient."""
        if recipient not in self._store:
            return False
        _, expires_at, attempt_count = self._store[recipient]
        if attempt_count >= _MAX_ATTEMPTS:
            return False
        return self._now() <= expires_at
