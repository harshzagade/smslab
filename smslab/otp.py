"""In-memory OTP lifecycle simulation with digest-only storage."""

from __future__ import annotations

import hashlib
import hmac
import secrets
import time
from dataclasses import dataclass
from typing import Callable


@dataclass
class _OtpRecord:
    digest: bytes
    expires_at: float
    attempts: int = 0
    locked: bool = False


class OtpService:
    """Generate and verify OTPs without logging or persisting plaintext values."""

    def __init__(
        self,
        *,
        ttl_seconds: int = 300,
        max_attempts: int = 3,
        code_length: int = 6,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if not 1 <= ttl_seconds <= 86400:
            raise ValueError("ttl_seconds must be between 1 and 86400.")
        if not 1 <= max_attempts <= 10:
            raise ValueError("max_attempts must be between 1 and 10.")
        if not 4 <= code_length <= 10:
            raise ValueError("code_length must be between 4 and 10.")
        self._ttl = ttl_seconds
        self._max_attempts = max_attempts
        self._code_length = code_length
        self._clock = clock
        self._records: dict[str, _OtpRecord] = {}

    def issue(self, recipient: str) -> str:
        """Create an OTP; the caller receives plaintext once, storage keeps a digest."""
        upper = 10 ** self._code_length
        code = f"{secrets.randbelow(upper):0{self._code_length}d}"
        self._records[recipient] = _OtpRecord(
            digest=hashlib.sha256(code.encode("ascii")).digest(),
            expires_at=self._clock() + self._ttl,
        )
        return code

    def verify(self, recipient: str, submitted_code: str) -> str:
        """Return verified, wrong_code, expired, locked, or missing."""
        record = self._records.get(recipient)
        if record is None:
            return "missing"
        if record.locked:
            return "locked"
        if self._clock() >= record.expires_at:
            return "expired"

        candidate = hashlib.sha256(str(submitted_code).encode("utf-8")).digest()
        if hmac.compare_digest(candidate, record.digest):
            del self._records[recipient]
            return "verified"

        record.attempts += 1
        if record.attempts >= self._max_attempts:
            record.locked = True
            return "locked"
        return "wrong_code"

    def stored_digest(self, recipient: str) -> bytes | None:
        """Expose only the digest for safety tests and diagnostics."""
        record = self._records.get(recipient)
        return record.digest if record else None
