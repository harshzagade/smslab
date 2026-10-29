"""
smslab.transports.provider_base — Future provider transport interface (stub, not implemented).

IMPORTANT: This module contains NO implementation and NO network code.
ProviderTransport.send() raises NotImplementedError unconditionally.

This module exists solely to document the interface contract that a future real-provider
transport would need to satisfy, so that third-party integrators could write their own
provider outside of this package without modifying it.

HOW A FUTURE PROVIDER WOULD PLUG IN (design notes, not implemented in v1):
---------------------------------------------------------------------------
1. Subclass ProviderTransport (which itself subclasses Transport).
2. Override send() to call your SMS provider's API. You would need to add:
   - A network client (e.g., urllib.request or a third-party HTTP library) — NOT present here.
   - Authentication credentials (API key, auth token, etc.) — NOT present here.
   - Provider-specific request/response parsing — NOT present here.
3. Map the provider's response to a DeliveryResult:
   - 2xx HTTP response → status="delivered", fill provider_message_id
   - Transient 5xx → status="failed", error_type="TransientFailure"
   - Hard rejection → status="failed", error_type="PermanentFailure"
   - HTTP 429 → status="failed", error_type="RateLimited", set retry_after_ms
   - Timeout / connect error → status="failed", error_type="Timeout"
4. Register your transport class in the config loader under a transport name key
   (e.g., "transport": "twilio") — the config loader currently only accepts "mock"
   and would need to be extended to map names to classes.

Why is this not implemented?
SMSLab's core value is being safe by construction: it structurally cannot send real SMS.
Adding a real provider would break that guarantee. This stub is a reference only.
"""

from __future__ import annotations

from smslab.transports.base import DeliveryResult, Transport

__all__ = ["ProviderTransport"]


class ProviderTransport(Transport):
    """Stub for a future real SMS provider transport.

    This class DOES NOT implement send(). Calling send() always raises NotImplementedError
    with a message explaining that real providers are not implemented in v1 and that this
    tool is mock-only by design.

    See module docstring for how a future real provider could implement this interface.
    """

    def send(self, recipient: str, body: str, *, timeout_ms: int) -> DeliveryResult:
        """Not implemented — SMSLab is mock-only in v1.

        Real provider transports are intentionally not implemented. This tool is designed
        for local integration testing with deterministic mock behaviour. If you need to
        test against a real SMS gateway, you should call that gateway's SDK directly in
        your own test suite — not through SMSLab.

        Raises:
            NotImplementedError: always.
        """
        raise NotImplementedError(
            "ProviderTransport.send() is not implemented. "
            "SMSLab v1 is mock-only by design — no real SMS providers are supported. "
            "Use MockTransport (transport = 'mock' in config) for all testing. "
            "See smslab/transports/provider_base.py for how a future provider would plug in."
        )
