"""
smslab.config — Configuration loading and validation.

Loads a JSON config file, validates all fields, normalises phone numbers, and
produces immutable dataclass objects consumed by the runner.

Hard caps (enforced, not silently clamped):
  max_cases   <= 200
  concurrency <= 10
  timeout_ms  <= 10000
  total messages across all cases <= 500

Transport must be "mock". Any other value is rejected.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from smslab.phones import PhoneValidationError, normalize_indian, validate_e164
from smslab.transports.mock import SUPPORTED_SCENARIOS

__all__ = ["ConfigError", "CaseConfig", "LimitsConfig", "Config", "load_config"]

# ---------------------------------------------------------------------------
# Hard caps
# ---------------------------------------------------------------------------
_CAP_MAX_CASES = 200
_CAP_CONCURRENCY = 10
_CAP_TIMEOUT_MS = 10_000
_CAP_TOTAL_MESSAGES = 500

# Allowed top-level keys
_TOP_LEVEL_KEYS = frozenset(
    {"transport", "seed", "limits", "test_recipients", "cases"}
)

# Allowed limits keys
_LIMITS_KEYS = frozenset({"max_cases", "concurrency", "timeout_ms"})

# Allowed case keys
_CASE_KEYS = frozenset({"name", "kind", "recipient", "body", "scenario", "expected"})

# Allowed values
_ALLOWED_TRANSPORTS = frozenset({"mock"})
_ALLOWED_KINDS = frozenset({"sms", "otp"})
_ALLOWED_EXPECTED = frozenset({"delivered", "failed", "verified", "wrong_code"})


class ConfigError(ValueError):
    """Raised when the configuration is invalid.

    The error message includes the field path to identify the problem location.
    """


# ---------------------------------------------------------------------------
# Config dataclasses
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class LimitsConfig:
    max_cases: int
    concurrency: int
    timeout_ms: int


@dataclass(frozen=True)
class CaseConfig:
    name: str
    kind: str           # "sms" | "otp"
    recipient: str      # normalised E.164
    scenario: str
    expected: str       # "delivered" | "failed" | "verified" | "wrong_code"
    body: Optional[str] = None  # required for sms, None for otp


@dataclass(frozen=True)
class Config:
    transport: str
    seed: int
    limits: LimitsConfig
    test_recipients: List[str]  # normalised E.164
    cases: List[CaseConfig]


# ---------------------------------------------------------------------------
# Loader
# ---------------------------------------------------------------------------


def load_config(path: str | Path) -> Config:
    """Load and validate a config JSON file.

    Args:
        path: Path to the JSON config file.

    Returns:
        Validated Config dataclass.

    Raises:
        ConfigError: for any validation problem (with field path in message).
        FileNotFoundError: if the file does not exist.
        json.JSONDecodeError: if the file is not valid JSON (wrapped in ConfigError).
    """
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Config file not found: {p}")

    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ConfigError(f"Invalid JSON in config file: {exc}") from exc

    if not isinstance(raw, dict):
        raise ConfigError("Config must be a JSON object at the top level.")

    # Unknown top-level keys
    unknown = set(raw.keys()) - _TOP_LEVEL_KEYS
    if unknown:
        raise ConfigError(
            f"Unknown top-level key(s): {sorted(unknown)}. "
            f"Allowed: {sorted(_TOP_LEVEL_KEYS)}"
        )

    # --- transport ---
    transport = _require_str(raw, "transport", "transport")
    if transport not in _ALLOWED_TRANSPORTS:
        raise ConfigError(
            f"transport: {transport!r} is not supported. "
            f"SMSLab only supports transport='mock'. "
            f"Real provider transports are not implemented by design."
        )

    # --- seed ---
    seed = _require_int(raw, "seed", "seed")

    # --- limits ---
    limits_raw = raw.get("limits")
    if limits_raw is None:
        raise ConfigError("limits: field is required.")
    if not isinstance(limits_raw, dict):
        raise ConfigError("limits: must be a JSON object.")

    unknown_limits = set(limits_raw.keys()) - _LIMITS_KEYS
    if unknown_limits:
        raise ConfigError(
            f"limits: unknown key(s) {sorted(unknown_limits)}. "
            f"Allowed: {sorted(_LIMITS_KEYS)}"
        )

    max_cases = _require_int(limits_raw, "max_cases", "limits.max_cases")
    concurrency = _require_int(limits_raw, "concurrency", "limits.concurrency")
    timeout_ms = _require_int(limits_raw, "timeout_ms", "limits.timeout_ms")

    if max_cases < 1:
        raise ConfigError("limits.max_cases: must be >= 1.")
    if max_cases > _CAP_MAX_CASES:
        raise ConfigError(
            f"limits.max_cases: {max_cases} exceeds the hard cap of {_CAP_MAX_CASES}."
        )
    if concurrency < 1:
        raise ConfigError("limits.concurrency: must be >= 1.")
    if concurrency > _CAP_CONCURRENCY:
        raise ConfigError(
            f"limits.concurrency: {concurrency} exceeds the hard cap of {_CAP_CONCURRENCY}."
        )
    if timeout_ms < 1:
        raise ConfigError("limits.timeout_ms: must be >= 1.")
    if timeout_ms > _CAP_TIMEOUT_MS:
        raise ConfigError(
            f"limits.timeout_ms: {timeout_ms} exceeds the hard cap of {_CAP_TIMEOUT_MS}."
        )

    limits = LimitsConfig(
        max_cases=max_cases,
        concurrency=concurrency,
        timeout_ms=timeout_ms,
    )

    # --- test_recipients ---
    recipients_raw = raw.get("test_recipients")
    if recipients_raw is None:
        raise ConfigError("test_recipients: field is required.")
    if not isinstance(recipients_raw, list):
        raise ConfigError("test_recipients: must be a JSON array.")
    if len(recipients_raw) == 0:
        raise ConfigError("test_recipients: must contain at least one recipient.")

    test_recipients: List[str] = []
    for i, r in enumerate(recipients_raw):
        if not isinstance(r, str):
            raise ConfigError(
                f"test_recipients[{i}]: must be a string, got {type(r).__name__}."
            )
        normalised = _normalise_phone(r, f"test_recipients[{i}]")
        test_recipients.append(normalised)

    # Deduplicate (keep order)
    seen: set = set()
    deduped: List[str] = []
    for r in test_recipients:
        if r not in seen:
            seen.add(r)
            deduped.append(r)
    test_recipients = deduped

    # --- cases ---
    cases_raw = raw.get("cases")
    if cases_raw is None:
        raise ConfigError("cases: field is required.")
    if not isinstance(cases_raw, list):
        raise ConfigError("cases: must be a JSON array.")
    if len(cases_raw) == 0:
        raise ConfigError("cases: must contain at least one case.")
    if len(cases_raw) > max_cases:
        raise ConfigError(
            f"cases: {len(cases_raw)} cases exceeds limits.max_cases={max_cases}."
        )

    case_names: set = set()
    cases: List[CaseConfig] = []
    total_messages = 0

    for i, c in enumerate(cases_raw):
        prefix = f"cases[{i}]"
        if not isinstance(c, dict):
            raise ConfigError(f"{prefix}: each case must be a JSON object.")

        unknown_case = set(c.keys()) - _CASE_KEYS
        if unknown_case:
            raise ConfigError(
                f"{prefix}: unknown key(s) {sorted(unknown_case)}. "
                f"Allowed: {sorted(_CASE_KEYS)}"
            )

        name = _require_str(c, "name", f"{prefix}.name")
        if name in case_names:
            raise ConfigError(
                f"{prefix}.name: duplicate case name {name!r}. Case names must be unique."
            )
        case_names.add(name)

        kind = _require_str(c, "kind", f"{prefix}.kind")
        if kind not in _ALLOWED_KINDS:
            raise ConfigError(
                f"{prefix}.kind: {kind!r} is not valid. Allowed: {sorted(_ALLOWED_KINDS)}"
            )

        recipient_raw = _require_str(c, "recipient", f"{prefix}.recipient")
        recipient = _normalise_phone(recipient_raw, f"{prefix}.recipient")

        if recipient not in test_recipients:
            raise ConfigError(
                f"{prefix}.recipient: {recipient!r} (normalised from {recipient_raw!r}) "
                f"is not in test_recipients. Add it to the allowlist first."
            )

        scenario = _require_str(c, "scenario", f"{prefix}.scenario")
        if scenario not in SUPPORTED_SCENARIOS:
            raise ConfigError(
                f"{prefix}.scenario: {scenario!r} is not a supported scenario. "
                f"Supported: {sorted(SUPPORTED_SCENARIOS)}"
            )

        # OTP scenarios: otp_wrong_code is only valid for kind=otp
        if scenario == "otp_wrong_code" and kind != "otp":
            raise ConfigError(
                f"{prefix}.scenario: 'otp_wrong_code' is only valid for kind='otp'."
            )

        expected = _require_str(c, "expected", f"{prefix}.expected")
        if expected not in _ALLOWED_EXPECTED:
            raise ConfigError(
                f"{prefix}.expected: {expected!r} is not valid. "
                f"Allowed: {sorted(_ALLOWED_EXPECTED)}"
            )

        body: Optional[str] = None
        if kind == "sms":
            if "body" not in c:
                raise ConfigError(f"{prefix}.body: required for kind='sms'.")
            body = _require_str(c, "body", f"{prefix}.body")
            if not body.strip():
                raise ConfigError(f"{prefix}.body: must not be empty.")

        total_messages += 1
        if total_messages > _CAP_TOTAL_MESSAGES:
            raise ConfigError(
                f"Total messages across all cases ({total_messages}) exceeds the "
                f"hard cap of {_CAP_TOTAL_MESSAGES}."
            )

        cases.append(
            CaseConfig(
                name=name,
                kind=kind,
                recipient=recipient,
                scenario=scenario,
                expected=expected,
                body=body,
            )
        )

    return Config(
        transport=transport,
        seed=seed,
        limits=limits,
        test_recipients=test_recipients,
        cases=cases,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _require_str(obj: Dict[str, Any], key: str, path: str) -> str:
    if key not in obj:
        raise ConfigError(f"{path}: field is required.")
    val = obj[key]
    if not isinstance(val, str):
        raise ConfigError(
            f"{path}: must be a string, got {type(val).__name__}."
        )
    return val


def _require_int(obj: Dict[str, Any], key: str, path: str) -> int:
    if key not in obj:
        raise ConfigError(f"{path}: field is required.")
    val = obj[key]
    # JSON numbers: accept int; reject float, bool, str
    if isinstance(val, bool) or not isinstance(val, int):
        raise ConfigError(
            f"{path}: must be an integer, got {type(val).__name__} ({val!r})."
        )
    return val


def _normalise_phone(raw: str, path: str) -> str:
    """Try Indian normalisation first, then E.164 validation."""
    try:
        return normalize_indian(raw)
    except PhoneValidationError:
        pass
    try:
        return validate_e164(raw)
    except PhoneValidationError as exc:
        raise ConfigError(
            f"{path}: {raw!r} is not a valid Indian mobile or E.164 number. {exc}"
        ) from exc
