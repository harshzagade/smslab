"""
smslab.transports.base — Abstract transport protocol.

No network code is present in this module.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional

__all__ = ["DeliveryResult", "Transport"]


@dataclass
class DeliveryResult:
    """Result of a single SMS send attempt.

    Attributes:
        status: "delivered", "failed", or "timeout"
        latency_ms: simulated or actual latency in milliseconds
        provider_message_id: unique message ID from provider (mock or real), may be None on failure
        error_type: None for success; one of "TransientFailure", "PermanentFailure",
                    "RateLimited", "Timeout" for failures
        error_message: human-readable error message, None on success
        retry_after_ms: for RateLimited errors, suggested retry delay (optional)
    """

    status: str
    latency_ms: int
    provider_message_id: Optional[str] = None
    error_type: Optional[str] = None
    error_message: Optional[str] = None
    retry_after_ms: Optional[int] = None


class Transport(ABC):
    """Abstract base for SMS transports.

    All transports must implement send(). The only concrete transport in v1 is MockTransport.
    """

    @abstractmethod
    def send(self, recipient: str, body: str, *, timeout_ms: int) -> DeliveryResult:
        """Send an SMS message to the recipient.

        Args:
            recipient: E.164 phone number
            body: Message body text
            timeout_ms: Maximum allowed latency (milliseconds)

        Returns:
            DeliveryResult describing the outcome.
        """
        raise NotImplementedError
