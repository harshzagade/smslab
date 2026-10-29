"""Strict configuration loading and validation."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from smslab.phones import PhoneNumberError, normalize_indian_mobile

MAX_CASES = 100
MAX_CONCURRENCY = 10
MAX_REQUESTS = 1000
MAX_TIMEOUT_MS = 30000
SMS_SCENARIOS = {"success": "delivered", "transient_failure": "delivered", "permanent_failure": "failed", "timeout": "failed", "rate_limited": "failed"}
OTP_SCENARIOS = {"success": "verified", "wrong_code": "wrong_code", "expired": "expired", "lockout": "locked"}


class ConfigError(ValueError):
    """Raised when a config file violates the schema or hard safety bounds."""


@dataclass(frozen=True)
class TestCase:
    name: str
    kind: str
    recipient: str
    scenario: str
    expected: str


@dataclass(frozen=True)
class Limits:
    max_cases: int = MAX_CASES
    concurrency: int = MAX_CONCURRENCY
    timeout_ms: int = 3000
    max_requests: int = MAX_REQUESTS


@dataclass(frozen=True)
class Config:
    transport: str
    seed: int
    test_recipients: tuple[str, ...]
    cases: tuple[TestCase, ...]
    limits: Limits


def _positive_int(value: Any, field: str, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1 or value > maximum:
        raise ConfigError(f"limits.{field} must be an integer between 1 and {maximum}.")
    return value


def load_config(path: str | Path) -> Config:
    """Read JSON config, normalize test allowlist entries and enforce hard bounds."""
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
    except OSError as exc:
        raise ConfigError(f"Cannot read config file: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise ConfigError(f"Config is not valid JSON: {exc}") from exc
    if not isinstance(raw, dict):
        raise ConfigError("The top-level config must be a JSON object.")
    if raw.get("transport") != "mock":
        raise ConfigError("Only transport='mock' is supported; no real messaging transport exists.")
    seed = raw.get("seed", 42)
    if isinstance(seed, bool) or not isinstance(seed, int):
        raise ConfigError("seed must be an integer.")

    limits_raw = raw.get("limits", {})
    if not isinstance(limits_raw, dict):
        raise ConfigError("limits must be a JSON object.")
    limits = Limits(
        _positive_int(limits_raw.get("max_cases", MAX_CASES), "max_cases", MAX_CASES),
        _positive_int(limits_raw.get("concurrency", MAX_CONCURRENCY), "concurrency", MAX_CONCURRENCY),
        _positive_int(limits_raw.get("timeout_ms", 3000), "timeout_ms", MAX_TIMEOUT_MS),
        _positive_int(limits_raw.get("max_requests", MAX_REQUESTS), "max_requests", MAX_REQUESTS),
    )

    recipients_raw = raw.get("test_recipients")
    if not isinstance(recipients_raw, list) or not recipients_raw:
        raise ConfigError("test_recipients must be a non-empty array.")
    if len(recipients_raw) > MAX_CASES:
        raise ConfigError(f"At most {MAX_CASES} test recipients are permitted.")
    recipients: list[str] = []
    try:
        for item in recipients_raw:
            normalized = normalize_indian_mobile(item)
            if normalized in recipients:
                raise ConfigError(f"Duplicate test recipient after normalization: {normalized}")
            recipients.append(normalized)
    except PhoneNumberError as exc:
        raise ConfigError(f"Invalid test recipient: {exc}") from exc

    cases_raw = raw.get("cases")
    if not isinstance(cases_raw, list) or not cases_raw:
        raise ConfigError("cases must be a non-empty array.")
    if len(cases_raw) > limits.max_cases:
        raise ConfigError(f"Config contains {len(cases_raw)} cases, exceeding limits.max_cases={limits.max_cases}.")

    cases: list[TestCase] = []
    names: set[str] = set()
    for index, item in enumerate(cases_raw):
        location = f"cases[{index}]"
        if not isinstance(item, dict):
            raise ConfigError(f"{location} must be a JSON object.")
        name = item.get("name")
        if not isinstance(name, str) or not name.strip() or len(name) > 64:
            raise ConfigError(f"{location}.name must be 1–64 characters.")
        if name in names:
            raise ConfigError(f"Duplicate case name: {name}")
        names.add(name)

        kind = item.get("kind")
        if not isinstance(kind, str) or kind not in {"sms", "otp"}:
            raise ConfigError(f"{location}.kind must be 'sms' or 'otp'.")
        try:
            recipient = normalize_indian_mobile(item.get("recipient"))
        except PhoneNumberError as exc:
            raise ConfigError(f"{location}.recipient: {exc}") from exc
        if recipient not in recipients:
            raise ConfigError(f"{location} recipient {recipient} is not in test_recipients allowlist.")

        scenario = item.get("scenario")
        allowed = SMS_SCENARIOS if kind == "sms" else OTP_SCENARIOS
        if not isinstance(scenario, str) or scenario not in allowed:
            raise ConfigError(f"{location}.scenario is not supported for kind={kind}.")
        expected = item.get("expected", allowed[scenario])
        if not isinstance(expected, str) or not expected.strip():
            raise ConfigError(f"{location}.expected must be a non-empty string.")
        cases.append(TestCase(name, kind, recipient, scenario, expected))

    return Config("mock", seed, tuple(recipients), tuple(cases), limits)
