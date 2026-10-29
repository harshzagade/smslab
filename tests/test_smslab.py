"""Tests for the safe, local-only SMSLab simulation."""
from __future__ import annotations

import ast
import json
import tempfile
import unittest
from pathlib import Path

from smslab.cli import main
from smslab.burst import simulate_burst
from smslab.config import ConfigError, load_config
from smslab.otp import OtpService
from smslab.phones import PhoneNumberError, normalize_indian_mobile
from smslab.runner import run_cases
from smslab.transport import MockTransport

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "examples" / "config.example.json"
BANNED_IMPORTS = {"socket", "urllib", "http", "requests", "httpx", "aiohttp", "boto3", "twilio", "vonage"}


class TestPhones(unittest.TestCase):
    def test_normalization(self):
        for value in ("9876543210", "09876543210", "919876543210", "+919876543210", "+91 98765 43210", "(+91) 98765-43210"):
            with self.subTest(value=value):
                self.assertEqual(normalize_indian_mobile(value), "+919876543210")

    def test_invalid_values(self):
        for value in ("1234567890", "+14155550100", "98765", "abcdefghij", ""):
            with self.subTest(value=value):
                with self.assertRaises(PhoneNumberError):
                    normalize_indian_mobile(value)


class TestOtp(unittest.TestCase):
    def test_success_and_digest_only_storage(self):
        otp = OtpService()
        code = otp.issue("+919999999999")
        digest = otp.stored_digest("+919999999999")
        self.assertIsNotNone(digest)
        self.assertNotEqual(digest, code.encode("ascii"))
        self.assertEqual(otp.verify("+919999999999", code), "verified")
        self.assertIsNone(otp.stored_digest("+919999999999"))

    def test_lockout_after_three_bad_attempts(self):
        otp = OtpService(max_attempts=3)
        code = otp.issue("+919999999999")
        wrong = ("1" if code[0] != "1" else "2") + code[1:]
        self.assertEqual(otp.verify("+919999999999", wrong), "wrong_code")
        self.assertEqual(otp.verify("+919999999999", wrong), "wrong_code")
        self.assertEqual(otp.verify("+919999999999", wrong), "locked")
        self.assertEqual(otp.verify("+919999999999", code), "locked")

    def test_expiration_with_fake_clock(self):
        now = [10.0]
        otp = OtpService(ttl_seconds=30, clock=lambda: now[0])
        code = otp.issue("+919999999999")
        now[0] = 41.0
        self.assertEqual(otp.verify("+919999999999", code), "expired")


class TestConfig(unittest.TestCase):
    def test_sample_config_validates(self):
        config = load_config(EXAMPLE)
        self.assertEqual(config.transport, "mock")
        self.assertEqual(len(config.cases), 9)

    def test_non_mock_transport_rejected(self):
        raw = json.loads(EXAMPLE.read_text(encoding="utf-8"))
        raw["transport"] = "provider"
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "bad.json"
            path.write_text(json.dumps(raw), encoding="utf-8")
            with self.assertRaises(ConfigError):
                load_config(path)

    def test_hard_limit_cannot_be_raised(self):
        raw = json.loads(EXAMPLE.read_text(encoding="utf-8"))
        raw["limits"]["max_requests"] = 1001
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "bad.json"
            path.write_text(json.dumps(raw), encoding="utf-8")
            with self.assertRaises(ConfigError):
                load_config(path)

    def test_unallowlisted_recipient_rejected(self):
        raw = json.loads(EXAMPLE.read_text(encoding="utf-8"))
        raw["cases"][0]["recipient"] = "+919876543210"
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "bad.json"
            path.write_text(json.dumps(raw), encoding="utf-8")
            with self.assertRaises(ConfigError):
                load_config(path)


class TestRunner(unittest.TestCase):
    def test_all_sample_outcomes_match(self):
        report = run_cases(load_config(EXAMPLE), concurrency=3)
        self.assertEqual(report["summary"]["total"], 9)
        self.assertEqual(report["summary"]["failed"], 0)
        self.assertEqual(report["transport"], "mock")

    def test_transient_failure_retries_once(self):
        config = load_config(EXAMPLE)
        case = next(item for item in config.cases if item.scenario == "transient_failure")
        item = run_cases(config, [case], concurrency=1)["results"][0]
        self.assertEqual(item["actual"], "delivered")
        self.assertEqual(item["attempts"], 2)

    def test_timeout_is_simulated(self):
        result = MockTransport().send(scenario="timeout", request_index=1, attempt=1, timeout_ms=20)
        self.assertEqual(result.status, "failed")
        self.assertEqual(result.error_type, "Timeout")
        self.assertEqual(result.latency_ms, 21)


class TestCli(unittest.TestCase):
    def test_init_validate_run_and_bounded_loadtest(self):
        with tempfile.TemporaryDirectory() as td:
            config = Path(td) / "config.json"
            report = Path(td) / "report.json"
            self.assertEqual(main(["init", "--output", str(config)]), 0)
            self.assertEqual(main(["validate", "--config", str(config)]), 0)
            self.assertEqual(main(["run", "--config", str(config), "--report", str(report)]), 0)
            self.assertEqual(json.loads(report.read_text(encoding="utf-8"))["summary"]["total"], 6)
            load_report = Path(td) / "load.json"
            self.assertEqual(main(["loadtest", "--config", str(config), "--volume", "12", "--concurrency", "3", "--report", str(load_report)]), 0)
            self.assertEqual(json.loads(load_report.read_text(encoding="utf-8"))["summary"]["total"], 12)

    def test_existing_config_is_not_overwritten_unless_forced(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "config.json"
            path.write_text("keep", encoding="utf-8")
            self.assertEqual(main(["init", "--output", str(path)]), 2)
            self.assertEqual(path.read_text(encoding="utf-8"), "keep")

    def test_request_cap_enforced(self):
        with tempfile.TemporaryDirectory() as td:
            self.assertEqual(main(["loadtest", "--config", str(EXAMPLE), "--volume", "1001", "--report", str(Path(td) / "r.json")]), 2)


class TestMockBurst(unittest.TestCase):
    def test_ten_attempts_are_simulated_and_rate_limited(self):
        report = simulate_burst(attempts=10, limit=2, window_seconds=60)
        self.assertEqual(report["transport"], "none")
        self.assertEqual(report["actual_transmissions"], 0)
        self.assertEqual(report["summary"]["attempted"], 10)
        self.assertEqual(report["summary"]["accepted_by_mock_limiter"], 2)
        self.assertEqual(report["summary"]["rejected_rate_limit"], 8)
        self.assertTrue(all(item["sms_sent"] is False for item in report["results"]))
        self.assertTrue(all(item["recipient"] == "synthetic-test-recipient" for item in report["results"]))

    def test_invalid_bounds_are_rejected(self):
        for kwargs in (
            {"attempts": 0},
            {"attempts": 101},
            {"attempts": 2, "limit": 3},
            {"attempts": True},
        ):
            with self.subTest(kwargs=kwargs):
                with self.assertRaises(ValueError):
                    simulate_burst(**kwargs)

    def test_cli_writes_a_mock_only_report(self):
        with tempfile.TemporaryDirectory() as td:
            report_path = Path(td) / "burst.json"
            code = main([
                "mock-burst", "--attempts", "10", "--limit", "2",
                "--window-seconds", "60", "--report", str(report_path),
            ])
            saved = json.loads(report_path.read_text(encoding="utf-8"))
            self.assertEqual(code, 0)
            self.assertEqual(saved["summary"]["rejected_rate_limit"], 8)
            self.assertEqual(saved["actual_transmissions"], 0)


class TestSafety(unittest.TestCase):
    def test_package_imports_no_network_clients(self):
        package_files = list((ROOT / "smslab").rglob("*.py"))
        self.assertGreater(len(package_files), 0)
        for path in package_files:
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imported = [alias.name for alias in node.names]
                elif isinstance(node, ast.ImportFrom):
                    imported = [node.module or ""]
                else:
                    continue
                for module in imported:
                    self.assertNotIn(module.split(".")[0], BANNED_IMPORTS, f"{path.name} imports {module}")

    def test_non_mock_config_rejected(self):
        raw = json.loads(EXAMPLE.read_text(encoding="utf-8"))
        raw["transport"] = "http"
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "bad.json"
            path.write_text(json.dumps(raw), encoding="utf-8")
            with self.assertRaises(ConfigError):
                load_config(path)


if __name__ == "__main__":
    unittest.main()
