"""Tests for smslab.runner — end-to-end case execution with the example config."""

import json
import os
import tempfile
import unittest
from pathlib import Path

from smslab.config import load_config
from smslab.report import report_to_dict
from smslab.runner import run_cases


def _example_config_path() -> str:
    """Return the path to examples/config.example.json."""
    return str(Path(__file__).parent.parent / "examples" / "config.example.json")


class TestRunnerWithExampleConfig(unittest.TestCase):
    """End-to-end tests using the shipped example config."""

    def setUp(self):
        self.cfg = load_config(_example_config_path())
        self.report = run_cases(self.cfg, quiet=True)

    def test_all_six_cases_pass(self):
        """The example config must have 6 cases and all must pass."""
        self.assertEqual(self.report.summary.total, 6)
        self.assertEqual(self.report.summary.passed, 6)
        self.assertEqual(self.report.summary.failed, 0)

    def test_report_has_all_summary_fields(self):
        d = report_to_dict(self.report)
        self.assertIn("summary", d)
        summary = d["summary"]
        for field in ["total", "passed", "failed", "delivered", "errors_by_type",
                      "duration_ms", "throughput_per_s"]:
            self.assertIn(field, summary, f"Missing summary field: {field}")

    def test_report_has_results_list(self):
        d = report_to_dict(self.report)
        self.assertIn("results", d)
        self.assertEqual(len(d["results"]), 6)

    def test_report_result_has_required_fields(self):
        d = report_to_dict(self.report)
        required = ["name", "kind", "recipient", "scenario", "expected",
                    "actual_status", "outcome", "attempts", "latency_ms"]
        for result in d["results"]:
            for field in required:
                self.assertIn(field, result, f"Result missing field: {field}")

    def test_sms_success_case_delivered(self):
        results = {r.name: r for r in self.report.results}
        self.assertIn("sms_success", results)
        r = results["sms_success"]
        self.assertEqual(r.actual_status, "delivered")
        self.assertEqual(r.outcome, "pass")

    def test_sms_transient_failure_retries_and_delivers(self):
        results = {r.name: r for r in self.report.results}
        self.assertIn("sms_transient_failure", results)
        r = results["sms_transient_failure"]
        self.assertEqual(r.actual_status, "delivered")
        self.assertEqual(r.outcome, "pass")
        self.assertEqual(r.attempts, 2)  # original + 1 retry

    def test_sms_permanent_failure_fails(self):
        results = {r.name: r for r in self.report.results}
        r = results["sms_permanent_failure"]
        self.assertEqual(r.actual_status, "failed")
        self.assertEqual(r.outcome, "pass")

    def test_sms_rate_limited_fails(self):
        results = {r.name: r for r in self.report.results}
        r = results["sms_rate_limited"]
        self.assertEqual(r.actual_status, "failed")
        self.assertEqual(r.outcome, "pass")
        self.assertEqual(r.error_type, "RateLimited")

    def test_sms_timeout_fails(self):
        results = {r.name: r for r in self.report.results}
        r = results["sms_timeout"]
        self.assertEqual(r.actual_status, "failed")
        self.assertEqual(r.outcome, "pass")
        self.assertEqual(r.error_type, "Timeout")

    def test_otp_success_verified(self):
        results = {r.name: r for r in self.report.results}
        r = results["otp_success"]
        self.assertEqual(r.actual_status, "verified")
        self.assertEqual(r.outcome, "pass")

    def test_report_metadata(self):
        self.assertEqual(self.report.seed, 42)
        self.assertEqual(self.report.transport, "mock")
        self.assertIsNotNone(self.report.started_at)

    def test_duration_is_positive(self):
        self.assertGreater(self.report.summary.duration_ms, 0)

    def test_throughput_is_positive(self):
        self.assertGreater(self.report.summary.throughput_per_s, 0)


class TestRunnerWithLogFile(unittest.TestCase):

    def test_log_file_written(self):
        cfg = load_config(_example_config_path())
        with tempfile.TemporaryDirectory() as tmp:
            log_path = os.path.join(tmp, "run.log")
            run_cases(cfg, log_path=log_path, quiet=True)
            self.assertTrue(Path(log_path).exists())
            lines = Path(log_path).read_text().strip().split("\n")
            self.assertGreater(len(lines), 0)
            # Each line must be valid JSON
            for line in lines:
                if line.strip():
                    entry = json.loads(line)
                    self.assertIn("ts", entry)
                    self.assertIn("level", entry)
                    self.assertIn("event", entry)


class TestRunnerTransientRetry(unittest.TestCase):

    def test_transient_failure_case_has_two_attempts(self):
        """transient_failure case must show attempts=2 in the result."""
        cfg = load_config(_example_config_path())
        report = run_cases(cfg, quiet=True)
        results = {r.name: r for r in report.results}
        r = results["sms_transient_failure"]
        self.assertEqual(r.attempts, 2)

    def test_permanent_failure_case_has_one_attempt(self):
        """permanent_failure does not retry, so attempts=1."""
        cfg = load_config(_example_config_path())
        report = run_cases(cfg, quiet=True)
        results = {r.name: r for r in report.results}
        r = results["sms_permanent_failure"]
        self.assertEqual(r.attempts, 1)


class TestRunnerDeterminism(unittest.TestCase):

    def test_same_seed_produces_same_results(self):
        """Running twice with the same seed should produce the same outcomes."""
        cfg = load_config(_example_config_path())
        report1 = run_cases(cfg, quiet=True)
        report2 = run_cases(cfg, quiet=True)
        for r1, r2 in zip(report1.results, report2.results):
            self.assertEqual(r1.name, r2.name)
            self.assertEqual(r1.actual_status, r2.actual_status)
            self.assertEqual(r1.outcome, r2.outcome)


class TestRunnerReportSerialisation(unittest.TestCase):

    def test_report_to_dict_is_json_serialisable(self):
        cfg = load_config(_example_config_path())
        report = run_cases(cfg, quiet=True)
        d = report_to_dict(report)
        # Must not raise
        serialised = json.dumps(d)
        self.assertIsInstance(serialised, str)

    def test_report_dict_has_smslab_version(self):
        from smslab.report import report_to_dict
        cfg = load_config(_example_config_path())
        report = run_cases(cfg, quiet=True)
        d = report_to_dict(report)
        self.assertIn("smslab_version", d)
        self.assertEqual(d["smslab_version"], "1.0.0")


if __name__ == "__main__":
    unittest.main()
