"""Tests for smslab.phones — Indian phone normalization and E.164 validation."""

import unittest

from smslab.phones import (
    PhoneValidationError,
    is_valid_indian,
    normalize_indian,
    validate_e164,
)


class TestNormalizeIndian(unittest.TestCase):
    """Test all accepted input formats normalize to E.164."""

    # --- Accepted formats ---

    def test_e164_format(self):
        """'+91XXXXXXXXXX' normalises correctly."""
        self.assertEqual(normalize_indian("+919876543210"), "+919876543210")

    def test_country_code_without_plus(self):
        """'91XXXXXXXXXX' (12 digits, no +) normalises correctly."""
        self.assertEqual(normalize_indian("919876543210"), "+919876543210")

    def test_trunk_prefix(self):
        """'0XXXXXXXXXX' (11 digits, trunk prefix) normalises correctly."""
        self.assertEqual(normalize_indian("09876543210"), "+919876543210")

    def test_ten_digits(self):
        """'XXXXXXXXXX' (bare 10 digits) normalises correctly."""
        self.assertEqual(normalize_indian("9876543210"), "+919876543210")

    def test_with_spaces(self):
        """Strips spaces."""
        self.assertEqual(normalize_indian("98765 43210"), "+919876543210")

    def test_with_dashes(self):
        """Strips dashes."""
        self.assertEqual(normalize_indian("98765-43210"), "+919876543210")

    def test_with_parens(self):
        """Strips parentheses."""
        self.assertEqual(normalize_indian("(9876) 543210"), "+919876543210")

    def test_starts_with_6(self):
        """6-prefix subscriber number (e.g. Jio) is valid."""
        self.assertEqual(normalize_indian("6123456789"), "+916123456789")

    def test_starts_with_7(self):
        """7-prefix subscriber number is valid."""
        self.assertEqual(normalize_indian("7123456789"), "+917123456789")

    def test_starts_with_8(self):
        """8-prefix subscriber number is valid."""
        self.assertEqual(normalize_indian("8123456789"), "+918123456789")

    def test_starts_with_9(self):
        """9-prefix subscriber number is valid."""
        self.assertEqual(normalize_indian("9123456789"), "+919123456789")

    def test_e164_with_formatting(self):
        """'+91 98765 43210' with spaces normalises correctly."""
        self.assertEqual(normalize_indian("+91 98765 43210"), "+919876543210")

    # --- Error cases ---

    def test_empty_string(self):
        """Empty string raises PhoneValidationError with 'empty' in message."""
        with self.assertRaises(PhoneValidationError) as ctx:
            normalize_indian("")
        self.assertIn("empty", str(ctx.exception).lower())

    def test_whitespace_only(self):
        """Whitespace-only string raises PhoneValidationError with 'empty' in message."""
        with self.assertRaises(PhoneValidationError) as ctx:
            normalize_indian("   ")
        self.assertIn("empty", str(ctx.exception).lower())

    def test_junk_characters(self):
        """Non-numeric junk raises PhoneValidationError with 'non-numeric' in message."""
        with self.assertRaises(PhoneValidationError) as ctx:
            normalize_indian("abcdefghij")
        self.assertIn("non-numeric", str(ctx.exception).lower())

    def test_wrong_length_short(self):
        """Too-short number raises PhoneValidationError with 'length' in message."""
        with self.assertRaises(PhoneValidationError) as ctx:
            normalize_indian("98765")
        self.assertIn("length", str(ctx.exception).lower())

    def test_wrong_length_long(self):
        """Too-long number raises PhoneValidationError with 'length' in message."""
        with self.assertRaises(PhoneValidationError) as ctx:
            normalize_indian("9876543210123456")
        self.assertIn("length", str(ctx.exception).lower())

    def test_bad_first_digit_1(self):
        """Number starting with 1 raises PhoneValidationError about starting digit."""
        with self.assertRaises(PhoneValidationError) as ctx:
            normalize_indian("1234567890")
        self.assertIn("starting digit", str(ctx.exception).lower())

    def test_bad_first_digit_5(self):
        """Number starting with 5 raises PhoneValidationError about starting digit."""
        with self.assertRaises(PhoneValidationError) as ctx:
            normalize_indian("5234567890")
        self.assertIn("starting digit", str(ctx.exception).lower())

    def test_bad_first_digit_0(self):
        """10-digit number starting with 0 after stripping trunk prefix."""
        # "0012345678" is 10 digits starting with 0 — bare 10 but starts with 0
        with self.assertRaises(PhoneValidationError) as ctx:
            normalize_indian("0012345678")
        # Either wrong-length or bad-first-digit message
        msg = str(ctx.exception).lower()
        self.assertTrue("length" in msg or "starting digit" in msg)

    def test_wrong_country_code(self):
        """Number with +44 country code raises error about not +91."""
        with self.assertRaises(PhoneValidationError) as ctx:
            normalize_indian("+441234567890")
        self.assertIn("+91", str(ctx.exception))


class TestValidateE164(unittest.TestCase):
    """Test strict E.164 validation."""

    def test_valid_indian(self):
        result = validate_e164("+919876543210")
        self.assertEqual(result, "+919876543210")

    def test_valid_us(self):
        result = validate_e164("+12125551234")
        self.assertEqual(result, "+12125551234")

    def test_valid_uk(self):
        result = validate_e164("+441234567890")
        self.assertEqual(result, "+441234567890")

    def test_valid_min_length(self):
        """Minimum valid E.164: + then 8 digits."""
        result = validate_e164("+12345678")
        self.assertEqual(result, "+12345678")

    def test_valid_max_length(self):
        """Maximum valid E.164: + then 15 digits."""
        result = validate_e164("+122222222222222")  # 15 digits after +
        self.assertEqual(result, "+122222222222222")

    def test_missing_plus(self):
        """Missing + raises PhoneValidationError."""
        with self.assertRaises(PhoneValidationError) as ctx:
            validate_e164("919876543210")
        self.assertIn("'+'", str(ctx.exception))

    def test_empty(self):
        """Empty string raises with 'empty' in message."""
        with self.assertRaises(PhoneValidationError) as ctx:
            validate_e164("")
        self.assertIn("empty", str(ctx.exception).lower())

    def test_too_short(self):
        """Too few digits raises PhoneValidationError."""
        with self.assertRaises(PhoneValidationError) as ctx:
            validate_e164("+1234567")
        self.assertIn("short", str(ctx.exception).lower())

    def test_too_long(self):
        """Too many digits raises PhoneValidationError."""
        with self.assertRaises(PhoneValidationError) as ctx:
            validate_e164("+1234567890123456")  # 16 digits after + (max is 14)
        self.assertIn("long", str(ctx.exception).lower())

    def test_leading_zero_country_code(self):
        """Country code starting with 0 is invalid."""
        with self.assertRaises(PhoneValidationError) as ctx:
            validate_e164("+01234567890")
        self.assertIn("zero", str(ctx.exception).lower())

    def test_non_digit_after_plus(self):
        """Non-digit after '+' raises PhoneValidationError."""
        with self.assertRaises(PhoneValidationError) as ctx:
            validate_e164("+1abc5678")
        self.assertIn("non-digit", str(ctx.exception).lower())


class TestIsValidIndian(unittest.TestCase):
    """Test is_valid_indian — bool wrapper that never raises."""

    def test_valid_returns_true(self):
        self.assertTrue(is_valid_indian("9876543210"))
        self.assertTrue(is_valid_indian("+919876543210"))

    def test_invalid_returns_false(self):
        self.assertFalse(is_valid_indian("1234567890"))
        self.assertFalse(is_valid_indian(""))
        self.assertFalse(is_valid_indian("notanumber"))
        self.assertFalse(is_valid_indian("12345"))

    def test_never_raises(self):
        """is_valid_indian must not raise for any input."""
        for val in [None, 12345, [], {}, object()]:  # type: ignore[arg-type]
            try:
                result = is_valid_indian(val)  # type: ignore[arg-type]
                self.assertIsInstance(result, bool)
            except Exception as exc:
                self.fail(f"is_valid_indian raised {exc!r} for input {val!r}")


if __name__ == "__main__":
    unittest.main()
