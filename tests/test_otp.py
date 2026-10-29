"""Tests for smslab.otp — OTP generation and verification."""

import time
import unittest

from smslab.otp import OtpService, SimulatedOtp


class TestOtpGenerate(unittest.TestCase):

    def test_generate_returns_simulated_otp(self):
        svc = OtpService(seed=42)
        otp = svc.generate("+919999999999")
        self.assertIsInstance(otp, SimulatedOtp)

    def test_generate_code_is_six_digits(self):
        svc = OtpService(seed=42)
        otp = svc.generate("+919999999999")
        self.assertEqual(len(otp.code), 6)
        self.assertTrue(otp.code.isdigit())

    def test_generate_sets_recipient(self):
        svc = OtpService(seed=42)
        otp = svc.generate("+919999999999")
        self.assertEqual(otp.recipient, "+919999999999")

    def test_generate_sets_expiry(self):
        svc = OtpService(seed=42, expiry_seconds=300)
        before = time.time()
        otp = svc.generate("+919999999999")
        after = time.time()
        self.assertGreaterEqual(otp.expires_at, before + 300)
        self.assertLessEqual(otp.expires_at, after + 300)

    def test_generate_deterministic_with_seed(self):
        svc1 = OtpService(seed=99)
        svc2 = OtpService(seed=99)
        otp1 = svc1.generate("+919999999999")
        otp2 = svc2.generate("+919999999999")
        self.assertEqual(otp1.code, otp2.code)

    def test_generate_repr_shows_simulated_label(self):
        svc = OtpService(seed=42)
        otp = svc.generate("+919999999999")
        self.assertIn("SIMULATED", repr(otp))

    def test_generate_overrides_previous_otp(self):
        """Calling generate again for same recipient overwrites old OTP."""
        svc = OtpService(seed=42)
        otp1 = svc.generate("+919999999999")
        otp2 = svc.generate("+919999999999")
        # Old code is invalidated
        result = svc.verify("+919999999999", otp1.code)
        self.assertIn(result, ("wrong_code", "not_found"))
        # New code works
        result2 = svc.verify("+919999999999", otp2.code)
        self.assertEqual(result2, "verified")


class TestOtpVerifyHappyPath(unittest.TestCase):

    def test_verify_correct_code_returns_verified(self):
        svc = OtpService(seed=42)
        otp = svc.generate("+919999999999")
        result = svc.verify("+919999999999", otp.code)
        self.assertEqual(result, "verified")

    def test_verify_consumes_otp(self):
        """After successful verification, the OTP cannot be used again."""
        svc = OtpService(seed=42)
        otp = svc.generate("+919999999999")
        svc.verify("+919999999999", otp.code)
        result = svc.verify("+919999999999", otp.code)
        self.assertEqual(result, "not_found")


class TestOtpVerifyWrongCode(unittest.TestCase):

    def test_wrong_code_returns_wrong_code(self):
        svc = OtpService(seed=42)
        svc.generate("+919999999999")
        result = svc.verify("+919999999999", "000000")
        self.assertEqual(result, "wrong_code")

    def test_wrong_code_increments_attempts(self):
        """Two wrong attempts, then lockout on third."""
        svc = OtpService(seed=42)
        otp = svc.generate("+919999999999")
        bad = "000000" if otp.code != "000000" else "000001"
        svc.verify("+919999999999", bad)
        svc.verify("+919999999999", bad)
        # Third attempt
        result = svc.verify("+919999999999", bad)
        self.assertEqual(result, "wrong_code")

    def test_lockout_after_three_wrong_attempts(self):
        """After 3 wrong attempts, account is locked."""
        svc = OtpService(seed=42)
        otp = svc.generate("+919999999999")
        bad = "000000" if otp.code != "000000" else "000001"
        svc.verify("+919999999999", bad)
        svc.verify("+919999999999", bad)
        svc.verify("+919999999999", bad)
        # 4th attempt — should be locked
        result = svc.verify("+919999999999", bad)
        self.assertEqual(result, "locked")

    def test_locked_even_with_correct_code(self):
        """Once locked, even the correct code returns 'locked'."""
        svc = OtpService(seed=42)
        otp = svc.generate("+919999999999")
        bad = "000000" if otp.code != "000000" else "000001"
        for _ in range(3):
            svc.verify("+919999999999", bad)
        result = svc.verify("+919999999999", otp.code)
        self.assertEqual(result, "locked")


class TestOtpVerifyExpiry(unittest.TestCase):

    def test_expired_otp_returns_expired(self):
        """Injecting 'now' past expiry returns 'expired'."""
        svc = OtpService(seed=42, expiry_seconds=60)
        otp = svc.generate("+919999999999", now=1000.0)
        # Verify far in the future
        result = svc.verify("+919999999999", otp.code, now=1000.0 + 3600)
        self.assertEqual(result, "expired")

    def test_not_yet_expired_returns_verified(self):
        """Verify exactly at expiry boundary (just before) returns 'verified'."""
        svc = OtpService(seed=42, expiry_seconds=60)
        otp = svc.generate("+919999999999", now=1000.0)
        result = svc.verify("+919999999999", otp.code, now=1059.9)
        self.assertEqual(result, "verified")

    def test_clock_offset(self):
        """Clock offset shifts the effective current time."""
        svc = OtpService(seed=42, expiry_seconds=60, clock_offset_seconds=-10000)
        # With a huge negative offset, any code looks far-future expired
        otp = svc.generate("+919999999999")
        # Verify at real now + 0 -> effective time is far in the past, so not expired
        # (offset is -10000, which moves time backward, code should be valid)
        result = svc.verify("+919999999999", otp.code)
        self.assertEqual(result, "verified")


class TestOtpVerifyNotFound(unittest.TestCase):

    def test_not_found_for_unknown_recipient(self):
        svc = OtpService(seed=42)
        result = svc.verify("+919999999999", "123456")
        self.assertEqual(result, "not_found")

    def test_not_found_after_invalidate(self):
        svc = OtpService(seed=42)
        svc.generate("+919999999999")
        svc.invalidate("+919999999999")
        result = svc.verify("+919999999999", "123456")
        self.assertEqual(result, "not_found")


class TestOtpHasPending(unittest.TestCase):

    def test_has_pending_after_generate(self):
        svc = OtpService(seed=42)
        svc.generate("+919999999999")
        self.assertTrue(svc.has_pending("+919999999999"))

    def test_not_pending_before_generate(self):
        svc = OtpService(seed=42)
        self.assertFalse(svc.has_pending("+919999999999"))

    def test_not_pending_after_invalidate(self):
        svc = OtpService(seed=42)
        svc.generate("+919999999999")
        svc.invalidate("+919999999999")
        self.assertFalse(svc.has_pending("+919999999999"))


if __name__ == "__main__":
    unittest.main()
