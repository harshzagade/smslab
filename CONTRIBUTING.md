# Contributing to SMSLab

Thank you for your interest in contributing!

## Non-Negotiable Rule

**Pull requests that add real SMS sending capability will not be accepted, under any circumstances.**

This includes, but is not limited to:

- Adding a concrete transport that calls a real SMS provider API (Twilio, AWS SNS, Vonage, etc.)
- Adding any network code (socket, urllib, http.client, requests, httpx, aiohttp, subprocess with curl/wget, etc.)
- Adding dependencies that perform network I/O
- Adding features that could facilitate number harvesting, message bombing, CAPTCHA evasion, or rate-limit evasion
- Adding any feature whose purpose is to send real messages to real phones

SMSLab's entire value proposition is that it is **safe by construction**: it is structurally impossible
for it to send a real SMS. Adding network capability would destroy that guarantee.

## What We Welcome

- Bug fixes and correctness improvements
- Improvements to the mock scenario model (e.g. new deterministic scenarios)
- Better error messages and diagnostics
- Documentation improvements
- Additional test coverage
- Performance improvements (within the stdlib-only constraint)
- Support for additional phone number formats (with tests)

## Development Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
python3 -m unittest discover -s tests -v
```

## Code Style

- Python 3.10+
- Stdlib only — no third-party dependencies
- Type hints on all public functions
- Dataclasses for structured data
- All new public functions must have docstrings
- All new code must be covered by tests

## Submitting a PR

1. Fork the repository
2. Create a feature branch
3. Write tests first
4. Ensure `python3 -m unittest discover -s tests -v` passes with no failures
5. Open a pull request with a clear description
