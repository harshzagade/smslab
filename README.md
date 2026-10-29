# SMSLab

SMSLab is the single maintained repository for mock-only SMS/OTP scenario testing and bounded load simulation.

**No SMS is sent. No network transport exists.** It simulates application-facing outcomes entirely in-process, so it can be used for local development and CI without contacting a messaging provider.

## What it does

- Validate and normalize common Indian mobile-number formats to +91 E.164 format. This is format checking only; it does not verify number ownership or reachability.
- Run named SMS scenarios: success, retry after one transient failure, permanent failure, simulated timeout, and simulated rate limiting.
- Run OTP lifecycle scenarios: correct verification, wrong code, expiry, and lockout after repeated incorrect attempts.
- Run bounded concurrent load simulations with JSON reports for outcome counts, latency, error categories, and throughput.
- Reject non-mock transport configuration, non-allowlisted recipients, invalid settings, and requests beyond hard limits.
- Use Python's standard library at runtime; no third-party messaging SDKs are installed.

## Installation

Python 3.10 or later is required.

    git clone https://github.com/harshzagade/smslab.git
    cd smslab
    python -m pip install -e .
    smslab --help

On Kali Linux or another externally managed Python environment, use a virtual environment rather than installing into the system Python.

## Quick start

Create a starter config:

    smslab init --output my-config.json

Validate it:

    smslab validate --config my-config.json

Run its named scenarios:

    smslab run --config my-config.json --report report.json

Run a bounded simulated load test:

    smslab loadtest --config my-config.json --volume 100 --concurrency 5 --scenario success --report load-report.json

Check number formatting:

    smslab validate-phone 9876543210 "+91 98765 43210"

List scenarios:

    smslab scenarios --verbose

A nonzero CLI exit indicates a configuration/argument error or that one or more cases did not match their expected outcomes. Load-test volume is limited to 1,000 requests; concurrency is limited to 10 and also cannot exceed the config value. Timeout settings cannot exceed 30,000 ms.

## Safety model

- The only transport is the local MockTransport implementation.
- Any configuration whose transport field is not exactly mock is rejected.
- Recipients used by a test case must appear in the normalized test_recipients allowlist.
- Hard caps are checked in code and cannot be raised by a config.
- Mock timeout and rate-limit outcomes are simulated; the CLI does not wait for a carrier or make external requests.
- OTP values are held in memory for the verification flow; only SHA-256 digests are stored, and codes are not included in logs or reports.
- The automated tests scan the package for common networking imports.

SMSLab is not an SMS gateway, a message sender, or a tool for bypassing provider controls. Use it only to test your own application's logic.

## Configuration

The sample configuration is at examples/config.example.json. The transport must be mock. The test_recipients list is an allowlist; every configured case recipient must be in it. Each case contains a unique name, a kind (sms or otp), a recipient, and a supported scenario. The expected result defaults to the documented outcome for that scenario but can be set explicitly for negative tests.

Hard limits are fixed in code: 100 configured cases, 1,000 simulated requests per load run, 10 concurrent workers, and 30 seconds maximum configured timeout. The config may choose lower caps, but never higher ones.

## Reports

JSON reports include schema version, timestamp, seed, simulated transport, concurrency, summary totals, expected-outcome pass/fail, simulated deliveries, latency, throughput, error types, and per-case outcomes. They never include OTP plaintext values.

## Development and tests

From the repository root, run:

    python -m compileall -q smslab
    python -m unittest discover -s tests -v
    smslab loadtest --config examples/config.example.json --volume 5 --concurrency 2 --report /tmp/smslab-report.json

GitHub Actions runs the test suite and a load-test smoke test on Python 3.10, 3.11, and 3.12 for pushes and pull requests.

## Project structure

- smslab/phones.py — Indian mobile-number format normalization
- smslab/config.py — schema validation, allowlist and hard limits
- smslab/transport.py — local-only simulated SMS transport
- smslab/otp.py — OTP expiry, verification, digest storage, and lockout
- smslab/runner.py — concurrent scenario execution and JSON reporting
- smslab/cli.py — command-line interface
- tests/test_smslab.py — unit, integration, and safety checks

## Project history

SMSLab consolidates the scenario-testing work previously in SMSLab with the bounded mock load-simulation scope previously held in SMSWarm. SMSLab is the canonical active repository; the SMSWarm repository is retained as an archival pointer for old links.

## License

MIT. See LICENSE.
