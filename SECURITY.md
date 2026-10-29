# Security Policy

## Mock-Only Design

**SMSLab is strictly mock-only by design.**

- No SMS, no OTP, and no network traffic is ever sent from this tool.
- There is no transport other than `MockTransport`. The codebase contains no socket, urllib, http.client,
  or requests usage. This is enforced by an automated test (`tests/test_safety.py`).
- The `ProviderTransport` stub in `smslab/transports/provider_base.py` exists solely as documentation
  for future interface compatibility; its `send()` raises `NotImplementedError` unconditionally.
- Configs specifying `"transport": "anything_other_than_mock"` are rejected at validation time with
  exit code 2 — no case is ever executed.

## Intended Usage

SMSLab is a **developer tool** meant to run in local development or CI environments. It tests how
your application code handles various SMS/OTP outcomes (success, failures, timeouts, rate-limits)
without needing a real SMS gateway account or risking charges.

**Do not use real phone numbers as test recipients.** Use E.164 placeholder numbers that are not
real mobile subscribers, exactly as shown in the example config.

## What Is Not a Security Issue

The following are **by design** and not considered security vulnerabilities:

- The tool can only simulate SMS delivery — it will never contact any SMS provider.
- OTPs generated are for local developer simulation; they have no real-world validity.
- The log output contains simulated phone numbers (from your config); treat logs with care if
  your config contains real numbers.

## Reporting Issues

If you discover a bug, a design concern, or a potential misuse vector, please open a GitHub issue
describing the problem. For sensitive concerns, email the maintainer directly before public disclosure.

**Contributions that add real SMS sending capability will not be accepted.** See `CONTRIBUTING.md`.
