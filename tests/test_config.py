"""Tests for smslab.config — configuration loading and validation errors."""

import json
import os
import tempfile
import unittest
from pathlib import Path

from smslab.config import ConfigError, load_config


def _write_config(tmp_dir: str, data: dict) -> str:
    """Write a config dict to a temp JSON file and return the path."""
    path = os.path.join(tmp_dir, "config.json")
    Path(path).write_text(json.dumps(data), encoding="utf-8")
    return path


def _base_config() -> dict:
    """Return a minimal valid config dict."""
    return {
        "transport": "mock",
        "seed": 42,
        "limits": {"max_cases": 10, "concurrency": 2, "timeout_ms": 3000},
        "test_recipients": ["+919999999999"],
        "cases": [
            {
                "name": "test_case",
                "kind": "sms",
                "recipient": "+919999999999",
                "body": "Hello",
                "scenario": "success",
                "expected": "delivered",
            }
        ],
    }


class TestValidConfig(unittest.TestCase):

    def test_valid_config_loads(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = _write_config(tmp, _base_config())
            cfg = load_config(path)
            self.assertEqual(cfg.transport, "mock")
            self.assertEqual(cfg.seed, 42)
            self.assertEqual(len(cfg.cases), 1)
            self.assertEqual(len(cfg.test_recipients), 1)

    def test_recipient_normalised_to_e164(self):
        """Recipient in '9876543210' format is normalised to '+91...' in the loaded config."""
        data = _base_config()
        data["test_recipients"] = ["9876543210"]
        data["cases"][0]["recipient"] = "9876543210"
        with tempfile.TemporaryDirectory() as tmp:
            path = _write_config(tmp, data)
            cfg = load_config(path)
            self.assertEqual(cfg.test_recipients[0], "+919876543210")
            self.assertEqual(cfg.cases[0].recipient, "+919876543210")

    def test_otp_case_no_body_required(self):
        data = _base_config()
        data["cases"] = [
            {
                "name": "otp_test",
                "kind": "otp",
                "recipient": "+919999999999",
                "scenario": "success",
                "expected": "verified",
            }
        ]
        with tempfile.TemporaryDirectory() as tmp:
            path = _write_config(tmp, data)
            cfg = load_config(path)
            self.assertIsNone(cfg.cases[0].body)


class TestTransportValidation(unittest.TestCase):

    def test_transport_not_mock_rejected(self):
        """transport != 'mock' raises ConfigError."""
        data = _base_config()
        data["transport"] = "twilio"
        with tempfile.TemporaryDirectory() as tmp:
            path = _write_config(tmp, data)
            with self.assertRaises(ConfigError) as ctx:
                load_config(path)
            self.assertIn("mock", str(ctx.exception).lower())

    def test_transport_aws_sns_rejected(self):
        data = _base_config()
        data["transport"] = "aws_sns"
        with tempfile.TemporaryDirectory() as tmp:
            path = _write_config(tmp, data)
            with self.assertRaises(ConfigError):
                load_config(path)

    def test_transport_empty_string_rejected(self):
        data = _base_config()
        data["transport"] = ""
        with tempfile.TemporaryDirectory() as tmp:
            path = _write_config(tmp, data)
            with self.assertRaises(ConfigError):
                load_config(path)


class TestRecipientAllowlist(unittest.TestCase):

    def test_recipient_not_in_allowlist_rejected(self):
        """A case recipient not in test_recipients raises ConfigError."""
        data = _base_config()
        data["cases"][0]["recipient"] = "+918888888888"  # not in test_recipients
        with tempfile.TemporaryDirectory() as tmp:
            path = _write_config(tmp, data)
            with self.assertRaises(ConfigError) as ctx:
                load_config(path)
            self.assertIn("allowlist", str(ctx.exception).lower())

    def test_empty_test_recipients_rejected(self):
        data = _base_config()
        data["test_recipients"] = []
        with tempfile.TemporaryDirectory() as tmp:
            path = _write_config(tmp, data)
            with self.assertRaises(ConfigError):
                load_config(path)


class TestCapsEnforcement(unittest.TestCase):

    def test_max_cases_exceeded(self):
        """max_cases > 200 raises ConfigError with field path."""
        data = _base_config()
        data["limits"]["max_cases"] = 201
        with tempfile.TemporaryDirectory() as tmp:
            path = _write_config(tmp, data)
            with self.assertRaises(ConfigError) as ctx:
                load_config(path)
            self.assertIn("max_cases", str(ctx.exception))

    def test_concurrency_exceeded(self):
        """concurrency > 10 raises ConfigError with field path."""
        data = _base_config()
        data["limits"]["concurrency"] = 11
        with tempfile.TemporaryDirectory() as tmp:
            path = _write_config(tmp, data)
            with self.assertRaises(ConfigError) as ctx:
                load_config(path)
            self.assertIn("concurrency", str(ctx.exception))

    def test_timeout_ms_exceeded(self):
        """timeout_ms > 10000 raises ConfigError with field path."""
        data = _base_config()
        data["limits"]["timeout_ms"] = 10001
        with tempfile.TemporaryDirectory() as tmp:
            path = _write_config(tmp, data)
            with self.assertRaises(ConfigError) as ctx:
                load_config(path)
            self.assertIn("timeout_ms", str(ctx.exception))

    def test_cases_exceed_max_cases_limit(self):
        """More cases than limits.max_cases raises ConfigError."""
        data = _base_config()
        data["limits"]["max_cases"] = 2
        data["test_recipients"] = ["+919999999999"]
        data["cases"] = [
            {
                "name": f"case_{i}",
                "kind": "sms",
                "recipient": "+919999999999",
                "body": "Hi",
                "scenario": "success",
                "expected": "delivered",
            }
            for i in range(3)
        ]
        with tempfile.TemporaryDirectory() as tmp:
            path = _write_config(tmp, data)
            with self.assertRaises(ConfigError):
                load_config(path)

    def test_total_messages_cap(self):
        """Total messages > 500 across all cases raises ConfigError."""
        data = _base_config()
        data["limits"]["max_cases"] = 200
        data["test_recipients"] = ["+919999999999"]
        data["cases"] = [
            {
                "name": f"case_{i}",
                "kind": "sms",
                "recipient": "+919999999999",
                "body": "Hi",
                "scenario": "success",
                "expected": "delivered",
            }
            for i in range(501)
        ]
        with tempfile.TemporaryDirectory() as tmp:
            path = _write_config(tmp, data)
            with self.assertRaises(ConfigError):
                load_config(path)


class TestDuplicateCaseNames(unittest.TestCase):

    def test_duplicate_case_names_rejected(self):
        data = _base_config()
        data["cases"].append({
            "name": "test_case",  # same name
            "kind": "sms",
            "recipient": "+919999999999",
            "body": "Hi again",
            "scenario": "success",
            "expected": "delivered",
        })
        with tempfile.TemporaryDirectory() as tmp:
            path = _write_config(tmp, data)
            with self.assertRaises(ConfigError) as ctx:
                load_config(path)
            self.assertIn("duplicate", str(ctx.exception).lower())


class TestUnknownKeys(unittest.TestCase):

    def test_unknown_top_level_key_rejected(self):
        data = _base_config()
        data["unknown_field"] = "oops"
        with tempfile.TemporaryDirectory() as tmp:
            path = _write_config(tmp, data)
            with self.assertRaises(ConfigError) as ctx:
                load_config(path)
            self.assertIn("unknown", str(ctx.exception).lower())

    def test_unknown_case_key_rejected(self):
        data = _base_config()
        data["cases"][0]["extra_key"] = "oops"
        with tempfile.TemporaryDirectory() as tmp:
            path = _write_config(tmp, data)
            with self.assertRaises(ConfigError) as ctx:
                load_config(path)
            self.assertIn("unknown", str(ctx.exception).lower())


class TestUnknownScenario(unittest.TestCase):

    def test_unknown_scenario_rejected(self):
        data = _base_config()
        data["cases"][0]["scenario"] = "magical_delivery"
        with tempfile.TemporaryDirectory() as tmp:
            path = _write_config(tmp, data)
            with self.assertRaises(ConfigError) as ctx:
                load_config(path)
            self.assertIn("scenario", str(ctx.exception).lower())

    def test_otp_wrong_code_only_valid_for_otp_kind(self):
        """otp_wrong_code scenario on an sms kind case raises ConfigError."""
        data = _base_config()
        data["cases"][0]["scenario"] = "otp_wrong_code"
        with tempfile.TemporaryDirectory() as tmp:
            path = _write_config(tmp, data)
            with self.assertRaises(ConfigError):
                load_config(path)


class TestFieldRequirements(unittest.TestCase):

    def test_missing_transport(self):
        data = _base_config()
        del data["transport"]
        with tempfile.TemporaryDirectory() as tmp:
            path = _write_config(tmp, data)
            with self.assertRaises(ConfigError) as ctx:
                load_config(path)
            self.assertIn("transport", str(ctx.exception))

    def test_missing_body_for_sms(self):
        data = _base_config()
        del data["cases"][0]["body"]
        with tempfile.TemporaryDirectory() as tmp:
            path = _write_config(tmp, data)
            with self.assertRaises(ConfigError) as ctx:
                load_config(path)
            self.assertIn("body", str(ctx.exception))

    def test_empty_cases_rejected(self):
        data = _base_config()
        data["cases"] = []
        with tempfile.TemporaryDirectory() as tmp:
            path = _write_config(tmp, data)
            with self.assertRaises(ConfigError):
                load_config(path)

    def test_file_not_found(self):
        with self.assertRaises(FileNotFoundError):
            load_config("/nonexistent/path/config.json")

    def test_invalid_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "config.json")
            Path(path).write_text("{ not valid json }", encoding="utf-8")
            with self.assertRaises(ConfigError):
                load_config(path)


if __name__ == "__main__":
    unittest.main()
