# SMSLab

**Mock-first SMS/OTP integration testing CLI — no real SMS is ever sent.**

SMSLab is a developer tool for testing how your application handles various SMS and OTP delivery scenarios in a local environment. It gives you a deterministic, seed-driven mock that simulates success, transient failures, permanent failures, timeouts, and rate-limiting — without touching any real SMS gateway.

---

## What it is / is not

| It is | It is not |
|---|---|
| A local integration test harness for SMS/OTP logic | An SMS gateway or messaging service |
| Deterministic (seed-driven, reproducible) | Random or non-deterministic by default |
| Safe by construction (no network code exists in the package) | A wrapper around Twilio, AWS SNS, Vonage, or any real provider |
| A stdlib-only Python CLI (no pip dependencies) | A production SMS sender |
| A tool for CI pipelines | A rate-limit bypass or message bomber |

**The mock transport is the only transport.** Any config file that sets `"transport"` to anything other than `"mock"` is rejected at validation time with exit code 2.

---

## Features

- Six mock scenarios: `success`, `transient_failure`, `permanent_failure`, `timeout`, `rate_limited`, `otp_wrong_code`
- Indian phone number normalisation (E.164): accepts `+91XXXXXXXXXX`, `91XXXXXXXXXX`, `0XXXXXXXXXX`, `XXXXXXXXXX`
- OTP simulation: 6-digit codes, SHA-256 hash storage, 3-attempt lockout, configurable expiry, injectable clock for tests
- Concurrent case execution with `ThreadPoolExecutor` (concurrency up to 10)
- Structured JSON logging per case event
- Hard caps on cases, concurrency, timeouts, and total messages — never silently clamped
- JSON report output + readable text summary
- Recipient allowlist enforcement before any case runs
- Stdlib only — no third-party dependencies required

---

## Installing on Kali Linux

Kali Linux (and other modern Debian-based systems) follows [PEP 668](https://peps.python.org/pep-0668/),
which marks the system Python as an "externally managed environment". This means `pip install` to the
system Python is blocked to protect system packages. **Do not use `--break-system-packages`.** Use a
virtual environment instead:

```bash
# Create a virtual environment
python3 -m venv .venv

# Activate it (do this once per terminal session)
source .venv/bin/activate

# Install SMSLab in editable mode (no external dependencies)
pip install -e .

# Verify
smslab --help
```

> The `.venv` directory is in `.gitignore` and will not be committed.

---

## Quickstart

### 1. Scaffold a config file

```bash
smslab init --output my-config.json
```

Expected output:
```
Config written to: my-config.json
Next steps:
  smslab validate --config my-config.json
  smslab run --config my-config.json --report report.json
```

### 2. Validate a phone number

```bash
smslab validate-phone 9876543210
smslab validate-phone "+91 98765 43210" 08888888888
```

Expected output:
```
9876543210 -> +919876543210 (valid Indian mobile)
+91 98765 43210 -> +919876543210 (valid Indian mobile)
08888888888 -> +918888888888 (valid Indian mobile)
```

### 3. Validate the config

```bash
smslab validate --config my-config.json
```

Expected output:
```
Config OK: 6 cases, 3 test recipients, transport=mock
```

### 4. Run the test cases

```bash
smslab run --config my-config.json --report report.json
```

Expected output:
```
SMSLab run: 6 cases, concurrency=4, seed=42

  ✓ PASS [sms] sms_success                       scenario=success               actual=delivered     expected=delivered
  ✓ PASS [sms] sms_transient_failure              scenario=transient_failure     actual=delivered     expected=delivered
  ✓ PASS [sms] sms_permanent_failure              scenario=permanent_failure     actual=failed        expected=failed
  ✓ PASS [sms] sms_rate_limited                   scenario=rate_limited          actual=failed        expected=failed
  ✓ PASS [sms] sms_timeout                        scenario=timeout               actual=failed        expected=failed
  ✓ PASS [otp] otp_success                        scenario=success               actual=verified      expected=verified

======================================================================
  SMSLab Run Report
======================================================================
  Started:    2026-10-30T...
  Transport:  mock
  Seed:       42
  Duration:   NNN ms  (X.XX cases/s)
----------------------------------------------------------------------
  Total:      6
  Passed:     6
  Failed:     0
  Delivered:  2
  Errors by type:
    PermanentFailure       1
    RateLimited            1
    Timeout                1
----------------------------------------------------------------------
  Case Results:
  ...
======================================================================
  ALL CASES PASSED
======================================================================

Report written to: report.json
```

### List all scenarios

```bash
smslab scenarios
```

---

## Scenario table

| Scenario | Kind | Description |
|---|---|---|
| `success` | sms, otp | Delivered/verified after simulated latency 20–120 ms |
| `transient_failure` | sms | First attempt fails (TransientFailure); a single retry succeeds |
| `permanent_failure` | sms | Always fails (PermanentFailure) — landline, DND, etc. |
| `timeout` | sms | Simulated latency exceeds `timeout_ms`; classified as Timeout |
| `rate_limited` | sms | Provider returns 429 with `retry_after_ms` hint |
| `otp_wrong_code` | otp | First verify attempt uses a wrong code; result is `wrong_code` |

---

## Config reference

```json
{
  "transport": "mock",
  "seed": 42,
  "limits": {
    "max_cases": 20,
    "concurrency": 4,
    "timeout_ms": 3000
  },
  "test_recipients": [
    "+919999999999",
    "+918888888888",
    "+917777777777"
  ],
  "cases": [
    {
      "name": "sms_success",
      "kind": "sms",
      "recipient": "+919999999999",
      "body": "Hello from SMSLab!",
      "scenario": "success",
      "expected": "delivered"
    },
    {
      "name": "otp_success",
      "kind": "otp",
      "recipient": "+917777777777",
      "scenario": "success",
      "expected": "verified"
    }
  ]
}
```

### Field reference

| Field | Type | Required | Description |
|---|---|---|---|
| `transport` | string | yes | Must be `"mock"` |
| `seed` | integer | yes | RNG seed for determinism |
| `limits.max_cases` | integer | yes | Hard cap: max 200 |
| `limits.concurrency` | integer | yes | Hard cap: max 10 |
| `limits.timeout_ms` | integer | yes | Hard cap: max 10000 |
| `test_recipients` | array of strings | yes | Phone number allowlist (E.164 or Indian format) |
| `cases[].name` | string | yes | Unique case name |
| `cases[].kind` | string | yes | `"sms"` or `"otp"` |
| `cases[].recipient` | string | yes | Must be in `test_recipients` |
| `cases[].body` | string | sms only | Message body text |
| `cases[].scenario` | string | yes | One of the six scenarios |
| `cases[].expected` | string | yes | `"delivered"`, `"failed"`, `"verified"`, or `"wrong_code"` |

### Hard caps (rejected, not clamped)

| Limit | Hard cap |
|---|---|
| `max_cases` | 200 |
| `concurrency` | 10 |
| `timeout_ms` | 10,000 ms |
| Total messages across all cases | 500 |

---

## Report format

The JSON report written by `smslab run` looks like:

```json
{
  "smslab_version": "1.0.0",
  "started_at": "2026-10-30T12:00:00.000000+00:00",
  "seed": 42,
  "transport": "mock",
  "summary": {
    "total": 6,
    "passed": 6,
    "failed": 0,
    "delivered": 4,
    "errors_by_type": {
      "PermanentFailure": 1,
      "RateLimited": 1,
      "Timeout": 1
    },
    "duration_ms": 312,
    "throughput_per_s": 19.23
  },
  "results": [
    {
      "name": "sms_success",
      "kind": "sms",
      "recipient": "+919999999999",
      "scenario": "success",
      "expected": "delivered",
      "actual_status": "delivered",
      "outcome": "pass",
      "attempts": 1,
      "latency_ms": 74
    }
  ]
}
```

---

## Safety design

SMSLab is safe by construction:

1. **No network code in the package.** The AST-based safety test (`tests/test_safety.py`) scans every `.py` file in `smslab/` for imports of `socket`, `urllib`, `http.client`, `requests`, and other networking modules. Any such import causes a test failure.

2. **Only `mock` transport accepted.** `load_config()` rejects any `"transport"` value other than `"mock"` with a `ConfigError` before a single case runs.

3. **`ProviderTransport.send()` raises `NotImplementedError`.** The provider stub in `smslab/transports/provider_base.py` documents the future interface but contains no implementation and no network calls.

4. **Recipient allowlist.** Every case recipient must appear in `test_recipients`. Runs are refused before execution if any recipient is missing from the allowlist.

5. **Hard caps.** Config files exceeding `max_cases=200`, `concurrency=10`, `timeout_ms=10000`, or 500 total messages are rejected — never silently clamped.

---

## Development

```bash
# Install in editable mode
python3 -m venv .venv
source .venv/bin/activate
pip install -e .

# Run the full test suite
python3 -m unittest discover -s tests -v

# Run a single test module
python3 -m unittest tests.test_phones -v
```

All tests use Python's standard `unittest` framework. No additional test dependencies are required.

---

## License

MIT — Copyright (c) 2026 Harsh Zagade. See [LICENSE](LICENSE).
