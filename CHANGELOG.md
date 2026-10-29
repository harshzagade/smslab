# Changelog

All notable changes to SMSLab will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] - 2026-10-30

### Added
- Initial release of SMSLab
- Mock-first SMS/OTP integration testing CLI
- `smslab init` — scaffold example config
- `smslab validate` — validate a config file
- `smslab validate-phone` — normalize and validate Indian mobile numbers
- `smslab run` — execute test cases and produce a JSON report
- `smslab scenarios` — list all supported mock scenarios
- Mock transport with scenarios: success, transient_failure, permanent_failure, timeout, rate_limited
- OTP simulation with generate/verify, lockout, and expiry
- Indian phone number normalization (E.164)
- Structured JSON logging per case event
- ThreadPoolExecutor-based concurrent case execution
- Hard caps on cases (200), concurrency (10), timeout_ms (10000), total messages (500)
- Strict allowlist enforcement: recipients must be declared in test_recipients
- Safety enforcement: no network code, no real SMS sending possible
- Stdlib-only — no third-party dependencies
- Full unittest test suite
