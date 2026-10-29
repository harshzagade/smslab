# Changelog

## 2.1.0 — Mock burst simulation

- Added `smslab mock-burst` for capped, in-process rate-limit demonstrations with synthetic recipients.
- Every burst result explicitly records that no SMS was sent; the command never accepts a phone-number target and has no network transport.
- Added unit tests and a CI smoke check for the default 10-attempt scenario (2 mock-accepted, 8 rate-limited, zero transmissions).

## 2.0.0 — Unified rebuild

- Rebuilt SMSLab as the canonical project combining scenario-based integration testing and bounded simulated load testing.
- Kept delivery transport strictly in-process and mock-only; no real SMS provider or network implementation exists.
- Added strict configuration validation, hard-coded upper bounds, Indian mobile number normalization, OTP expiry and lockout simulation, JSON reports, safety tests, and CI.
- SMSWarm is superseded by this repository; its repository now points here.
