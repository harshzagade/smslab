# Changelog

## 2.0.0 — Unified rebuild

- Rebuilt SMSLab as the canonical project combining scenario-based integration testing and bounded simulated load testing.
- Kept delivery transport strictly in-process and mock-only; no real SMS provider or network implementation exists.
- Added strict configuration validation, hard-coded upper bounds, Indian mobile number normalization, OTP expiry and lockout simulation, JSON reports, safety tests, and CI.
- SMSWarm is superseded by this repository; its repository now points here.
