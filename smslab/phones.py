"""
smslab.phones — Indian mobile number normalization and E.164 validation.

No network calls are made here. All validation is purely local string/regex logic.
"""

from __future__ import annotations

import re

__all__ = [
    "PhoneValidationError",
    "normalize_indian",
    "validate_e164",
    "is_valid_indian",
]

# E.164: + followed by 1-9, then 7-14 more digits (total 8-15 digits after +)
_E164_RE = re.compile(r"^\+[1-9]\d{7,14}$")

# Allowed first digits for Indian mobile numbers
_INDIAN_MOBILE_FIRST_DIGITS = frozenset("6789")


class PhoneValidationError(ValueError):
    """Raised when a phone number fails validation."""


def _strip_formatting(raw: str) -> str:
    """Remove spaces, dashes, parentheses, and dots from a phone string."""
    return re.sub(r"[\s\-().+]", "", raw)


def normalize_indian(raw: str) -> str:
    """Normalize an Indian mobile number to E.164 format (+91XXXXXXXXXX).

    Accepted input formats:
      - "+91XXXXXXXXXX"  — country code with plus, 12 chars after stripping
      - "91XXXXXXXXXX"   — country code without plus (12 digits)
      - "0XXXXXXXXXX"    — trunk prefix (11 digits)
      - "XXXXXXXXXX"     — 10-digit number

    Indian mobile numbers must be 10 digits and start with 6, 7, 8, or 9.

    Returns:
        E.164 string "+91XXXXXXXXXX"

    Raises:
        PhoneValidationError: with a specific message for each failure mode.
    """
    if not raw or not raw.strip():
        raise PhoneValidationError(
            "Phone number is empty. Provide a 10-digit Indian mobile number."
        )

    # Strip all formatting characters (spaces, dashes, parens, dots)
    # Keep the leading + temporarily to detect country code prefix
    stripped_plus = raw.strip()
    if stripped_plus.startswith("+"):
        digits_only = re.sub(r"[\s\-().]", "", stripped_plus[1:])
    else:
        digits_only = re.sub(r"[\s\-().]", "", stripped_plus)

    # Check for non-numeric junk after stripping formatting
    if not digits_only.isdigit():
        raise PhoneValidationError(
            f"Phone number contains non-numeric characters: {raw!r}. "
            "Only digits, spaces, dashes, and parentheses are allowed."
        )

    # Determine the 10-digit subscriber number
    if stripped_plus.startswith("+"):
        # "+91XXXXXXXXXX" — must be exactly "91" + 10 digits = 12 digits
        if not digits_only.startswith("91"):
            raise PhoneValidationError(
                f"Country code in {raw!r} is not +91 (India). "
                "Only Indian mobile numbers (+91) are supported."
            )
        subscriber = digits_only[2:]
    elif digits_only.startswith("91") and len(digits_only) == 12:
        # "91XXXXXXXXXX" — 12-digit form without +
        subscriber = digits_only[2:]
    elif digits_only.startswith("0") and len(digits_only) == 11:
        # "0XXXXXXXXXX" — trunk prefix
        subscriber = digits_only[1:]
    elif len(digits_only) == 10:
        # "XXXXXXXXXX" — bare 10 digits
        subscriber = digits_only
    else:
        raise PhoneValidationError(
            f"Wrong length for {raw!r}. Expected 10 digits (or 11 with trunk '0', "
            f"or 12 with country code '91'). Got {len(digits_only)} digits."
        )

    # Validate subscriber number length
    if len(subscriber) != 10:
        raise PhoneValidationError(
            f"Subscriber number derived from {raw!r} has {len(subscriber)} digits; "
            "expected exactly 10."
        )

    # Validate first digit of subscriber number
    if subscriber[0] not in _INDIAN_MOBILE_FIRST_DIGITS:
        raise PhoneValidationError(
            f"Invalid starting digit '{subscriber[0]}' in {raw!r}. "
            "Indian mobile numbers must start with 6, 7, 8, or 9."
        )

    return f"+91{subscriber}"


def validate_e164(raw: str) -> str:
    """Validate a phone number against the strict E.164 format.

    Format: '+' followed by a non-zero country code digit, then 7–14 more digits
    (total 8–15 digits after the '+', so 9–16 characters total).

    Returns:
        The input string unchanged if valid.

    Raises:
        PhoneValidationError: with a specific message if invalid.
    """
    if not raw or not raw.strip():
        raise PhoneValidationError(
            "Phone number is empty. E.164 format requires '+' followed by country "
            "code and subscriber number."
        )

    s = raw.strip()

    if not s.startswith("+"):
        raise PhoneValidationError(
            f"{raw!r} is missing the leading '+'. E.164 format requires '+' prefix "
            "followed by the country code (e.g. +919876543210)."
        )

    digits = s[1:]
    if not digits.isdigit():
        raise PhoneValidationError(
            f"{raw!r} contains non-digit characters after '+'. E.164 allows only "
            "digits after the '+' prefix."
        )

    if not _E164_RE.match(s):
        length = len(digits)
        if length < 8:
            raise PhoneValidationError(
                f"{raw!r} is too short ({length} digits after '+'). E.164 requires "
                "at least 8 digits after '+'."
            )
        if length > 15:
            raise PhoneValidationError(
                f"{raw!r} is too long ({length} digits after '+'). E.164 allows at "
                "most 15 digits after '+'."
            )
        if digits[0] == "0":
            raise PhoneValidationError(
                f"{raw!r} has a leading zero in the country code, which is not valid "
                "in E.164 format."
            )
        raise PhoneValidationError(
            f"{raw!r} is not a valid E.164 phone number. Expected format: "
            "'+[country-code][subscriber]', e.g. '+919876543210'."
        )

    return s


def is_valid_indian(raw: str) -> bool:
    """Return True if raw is a valid Indian mobile number (any supported format).

    Never raises; returns False for any invalid input.
    """
    try:
        normalize_indian(raw)
        return True
    except (PhoneValidationError, Exception):
        return False
