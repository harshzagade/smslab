"""Tests for smslab.cli — argument parsing and subcommand behavior."""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from smslab.cli import build_parser, main


def _write_valid_config(path: str) -> None:
    config = {
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
    Path(path).write_text(json.dumps(config), encoding="utf-8")


class TestBuildParser(unittest.TestCase):
    """Test that build_parser() produces correct arg structures."""

    def setUp(self):
        self.parser = build_parser()

    def test_init_subcommand_parses_output(self):
        args = self.parser.parse_args(["init", "--output", "config.json"])
        self.assertEqual(args.subcommand, "init")
        self.assertEqual(args.output, "config.json")
        self.assertFalse(args.force)

    def test_init_subcommand_with_force(self):
        args = self.parser.parse_args(["init", "--output", "config.json", "--force"])
        self.assertTrue(args.force)

    def test_validate_subcommand_parses_config(self):
        args = self.parser.parse_args(["validate", "--config", "my.json"])
        self.assertEqual(args.subcommand, "validate")
        self.assertEqual(args.config, "my.json")

    def test_validate_phone_subcommand_single(self):
        args = self.parser.parse_args(["validate-phone", "9876543210"])
        self.assertEqual(args.subcommand, "validate-phone")
        self.assertEqual(args.numbers, ["9876543210"])

    def test_validate_phone_subcommand_multiple(self):
        args = self.parser.parse_args(["validate-phone", "9876543210", "+918888888888"])
        self.assertEqual(args.numbers, ["9876543210", "+918888888888"])

    def test_run_subcommand_parses_required_args(self):
        args = self.parser.parse_args([
            "run", "--config", "c.json", "--report", "r.json"
        ])
        self.assertEqual(args.subcommand, "run")
        self.assertEqual(args.config, "c.json")
        self.assertEqual(args.report, "r.json")
        self.assertIsNone(args.log)
        self.assertFalse(args.quiet)

    def test_run_subcommand_with_log_and_quiet(self):
        args = self.parser.parse_args([
            "run", "--config", "c.json", "--report", "r.json", "--log", "l.json", "--quiet"
        ])
        self.assertEqual(args.log, "l.json")
        self.assertTrue(args.quiet)

    def test_scenarios_subcommand(self):
        args = self.parser.parse_args(["scenarios"])
        self.assertEqual(args.subcommand, "scenarios")

    def test_no_subcommand_sets_none(self):
        args = self.parser.parse_args([])
        self.assertIsNone(args.subcommand)


class TestCmdInit(unittest.TestCase):

    def test_init_creates_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = os.path.join(tmp, "test_config.json")
            with patch("sys.stdout", new_callable=StringIO) as mock_out:
                with self.assertRaises(SystemExit) as ctx:
                    main(["init", "--output", output])
            self.assertEqual(ctx.exception.code, 0)
            self.assertTrue(Path(output).exists())

    def test_init_creates_valid_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = os.path.join(tmp, "test_config.json")
            with patch("sys.stdout", new_callable=StringIO):
                with self.assertRaises(SystemExit):
                    main(["init", "--output", output])
            data = json.loads(Path(output).read_text())
            self.assertEqual(data["transport"], "mock")
            self.assertIn("cases", data)

    def test_init_refuses_overwrite_without_force(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = os.path.join(tmp, "test_config.json")
            Path(output).write_text("existing content")
            with patch("sys.stderr", new_callable=StringIO) as mock_err:
                with self.assertRaises(SystemExit) as ctx:
                    main(["init", "--output", output])
            self.assertEqual(ctx.exception.code, 2)
            self.assertIn("already exists", mock_err.getvalue())

    def test_init_force_overwrites(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = os.path.join(tmp, "test_config.json")
            Path(output).write_text("old content")
            with patch("sys.stdout", new_callable=StringIO):
                with self.assertRaises(SystemExit) as ctx:
                    main(["init", "--output", output, "--force"])
            self.assertEqual(ctx.exception.code, 0)
            data = json.loads(Path(output).read_text())
            self.assertEqual(data["transport"], "mock")


class TestCmdValidate(unittest.TestCase):

    def test_validate_valid_config_exit_0(self):
        with tempfile.TemporaryDirectory() as tmp:
            config_path = os.path.join(tmp, "c.json")
            _write_valid_config(config_path)
            with patch("sys.stdout", new_callable=StringIO) as mock_out:
                with self.assertRaises(SystemExit) as ctx:
                    main(["validate", "--config", config_path])
            self.assertEqual(ctx.exception.code, 0)
            self.assertIn("Config OK", mock_out.getvalue())

    def test_validate_nonexistent_config_exit_2(self):
        with patch("sys.stderr", new_callable=StringIO):
            with self.assertRaises(SystemExit) as ctx:
                main(["validate", "--config", "/nonexistent/config.json"])
        self.assertEqual(ctx.exception.code, 2)

    def test_validate_invalid_config_exit_2(self):
        with tempfile.TemporaryDirectory() as tmp:
            config_path = os.path.join(tmp, "c.json")
            Path(config_path).write_text(
                json.dumps({"transport": "twilio", "seed": 1,
                            "limits": {"max_cases": 10, "concurrency": 2, "timeout_ms": 1000},
                            "test_recipients": ["+919999999999"],
                            "cases": [{"name": "x", "kind": "sms", "recipient": "+919999999999",
                                       "body": "hi", "scenario": "success", "expected": "delivered"}]}),
                encoding="utf-8"
            )
            with patch("sys.stderr", new_callable=StringIO):
                with self.assertRaises(SystemExit) as ctx:
                    main(["validate", "--config", config_path])
        self.assertEqual(ctx.exception.code, 2)


class TestCmdValidatePhone(unittest.TestCase):

    def test_valid_number_exit_0(self):
        with patch("sys.stdout", new_callable=StringIO) as mock_out:
            with self.assertRaises(SystemExit) as ctx:
                main(["validate-phone", "9876543210"])
        self.assertEqual(ctx.exception.code, 0)
        self.assertIn("+919876543210", mock_out.getvalue())

    def test_invalid_number_exit_2(self):
        with patch("sys.stderr", new_callable=StringIO):
            with self.assertRaises(SystemExit) as ctx:
                main(["validate-phone", "1234567890"])
        self.assertEqual(ctx.exception.code, 2)

    def test_multiple_numbers_partial_failure_exit_2(self):
        """If any number is invalid, exit code is 2."""
        with patch("sys.stdout", new_callable=StringIO):
            with patch("sys.stderr", new_callable=StringIO):
                with self.assertRaises(SystemExit) as ctx:
                    main(["validate-phone", "9876543210", "1234567890"])
        self.assertEqual(ctx.exception.code, 2)

    def test_multiple_valid_numbers_exit_0(self):
        with patch("sys.stdout", new_callable=StringIO):
            with self.assertRaises(SystemExit) as ctx:
                main(["validate-phone", "9876543210", "+919999999999"])
        self.assertEqual(ctx.exception.code, 0)


class TestCmdRun(unittest.TestCase):

    def test_run_valid_config_exit_0(self):
        with tempfile.TemporaryDirectory() as tmp:
            config_path = os.path.join(tmp, "c.json")
            report_path = os.path.join(tmp, "r.json")
            _write_valid_config(config_path)
            with patch("sys.stdout", new_callable=StringIO):
                with self.assertRaises(SystemExit) as ctx:
                    main(["run", "--config", config_path, "--report", report_path])
            self.assertEqual(ctx.exception.code, 0)
            self.assertTrue(Path(report_path).exists())

    def test_run_writes_report_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            config_path = os.path.join(tmp, "c.json")
            report_path = os.path.join(tmp, "r.json")
            _write_valid_config(config_path)
            with patch("sys.stdout", new_callable=StringIO):
                with self.assertRaises(SystemExit):
                    main(["run", "--config", config_path, "--report", report_path])
            data = json.loads(Path(report_path).read_text())
            self.assertIn("summary", data)
            self.assertIn("results", data)

    def test_run_nonexistent_config_exit_2(self):
        with patch("sys.stderr", new_callable=StringIO):
            with self.assertRaises(SystemExit) as ctx:
                main(["run", "--config", "/no/such/file.json", "--report", "/tmp/r.json"])
        self.assertEqual(ctx.exception.code, 2)

    def test_run_all_fail_exit_1(self):
        """Config where all expected don't match should exit 1."""
        with tempfile.TemporaryDirectory() as tmp:
            # Use permanent_failure but expect delivered — will fail
            config = {
                "transport": "mock",
                "seed": 42,
                "limits": {"max_cases": 10, "concurrency": 1, "timeout_ms": 3000},
                "test_recipients": ["+919999999999"],
                "cases": [
                    {
                        "name": "will_fail",
                        "kind": "sms",
                        "recipient": "+919999999999",
                        "body": "Hi",
                        "scenario": "permanent_failure",
                        "expected": "delivered",  # wrong expectation
                    }
                ],
            }
            config_path = os.path.join(tmp, "c.json")
            report_path = os.path.join(tmp, "r.json")
            Path(config_path).write_text(json.dumps(config))
            with patch("sys.stdout", new_callable=StringIO):
                with self.assertRaises(SystemExit) as ctx:
                    main(["run", "--config", config_path, "--report", report_path])
            self.assertEqual(ctx.exception.code, 1)


class TestCmdScenarios(unittest.TestCase):

    def test_scenarios_exit_0(self):
        with patch("sys.stdout", new_callable=StringIO) as mock_out:
            with self.assertRaises(SystemExit) as ctx:
                main(["scenarios"])
        self.assertEqual(ctx.exception.code, 0)
        output = mock_out.getvalue()
        self.assertIn("success", output)
        self.assertIn("transient_failure", output)
        self.assertIn("permanent_failure", output)
        self.assertIn("timeout", output)
        self.assertIn("rate_limited", output)


class TestNoSubcommand(unittest.TestCase):

    def test_no_subcommand_exits_2(self):
        with patch("sys.stdout", new_callable=StringIO):
            with self.assertRaises(SystemExit) as ctx:
                main([])
        self.assertEqual(ctx.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
