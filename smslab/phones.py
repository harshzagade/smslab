"""Indian mobile-number formatting. This module does not verify ownership."""

from __future__ import annotations

import re


class PhoneNumberError(ValueError):
    """Raised when an input is not a supported Indian mobile-number format."""


def normalize_indian_mobile(value: str) -> str:
    """Normalize common Indian mobile formats to +91 followed by ten digits.

    Accepted examples: 9876543210, 09876543210, 919876543210, +91 98765 43210.
    This is format validation only; it does not check whether a number exists or
    who owns it.
    """
    if not isinstance(value, str):
        raise PhoneNumberError("Phone number must be text.")

    compact = re.sub(r"[\s()\-]", "", value)
    if compact.startswith("+"):
        compact = compact[1:]

    if len(compact) == 12 and compact.startswith("91"):
        digits = compact[2:]
    elif len(compact) == 11 and compact.startswith("0"):
        digits = compact[1:]
    elif len(compact) == 10:
        digits = compact
    else:
        raise PhoneNumberError("Use a 10-digit Indian mobile number, optionally prefixed by 0, 91, or +91.")

    if not re.fullmatch(r"[6-9][0-9]{9}", digits):
        raise PhoneNumberError("Indian mobile numbers must contain ten digits and start with 6, 7, 8, or 9.")

    return "+91" + digits
