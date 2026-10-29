"""Command-line interface for SMSLab."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from smslab import __version__
from smslab.burst import simulate_burst, write_burst_report
from smslab.config import MAX_CONCURRENCY, MAX_REQUESTS, SMS_SCENARIOS, ConfigError, TestCase, load_config
from smslab.phones import PhoneNumberError, normalize_indian_mobile
from smslab.runner import run_cases, write_report

EXAMPLE_CONFIG = {
    "transport": "mock",
    "seed": 42,
    "limits": {"max_cases": 100, "concurrency": 5, "timeout_ms": 3000, "max_requests": 1000},
    "test_recipients": ["+919999999999", "+918888888888", "+917777777777"],
    "cases": [
        {"name": "sms_success", "kind": "sms", "recipient": "+919999999999", "scenario": "success"},
        {"name": "sms_retry", "kind": "sms", "recipient": "+918888888888", "scenario": "transient_failure"},
        {"name": "sms_permanent_failure", "kind": "sms", "recipient": "+917777777777", "scenario": "permanent_failure"},
        {"name": "otp_success", "kind": "otp", "recipient": "+919999999999", "scenario": "success"},
        {"name": "otp_wrong_code", "kind": "otp", "recipient": "+918888888888", "scenario": "wrong_code"},
        {"name": "otp_expired", "kind": "otp", "recipient": "+917777777777", "scenario": "expired"},
    ],
}


def build_parser():
    parser = argparse.ArgumentParser(
        prog="smslab",
        description="Mock-only SMS/OTP scenario and bounded load testing. No real SMS is sent.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    subs = parser.add_subparsers(dest="command", required=True)

    init = subs.add_parser("init", help="Write a starter mock-only configuration.")
    init.add_argument("--output", required=True)
    init.add_argument("--force", action="store_true")

    phone = subs.add_parser("validate-phone", help="Format-check Indian mobile number(s).")
    phone.add_argument("numbers", nargs="+")

    validate = subs.add_parser("validate", help="Validate a config without running tests.")
    validate.add_argument("--config", required=True)

    scenarios = subs.add_parser("scenarios", help="List supported simulated scenarios.")
    scenarios.add_argument("--verbose", action="store_true")

    run = subs.add_parser("run", help="Run configured cases.")
    run.add_argument("--config", required=True)
    run.add_argument("--report", required=True)
    run.add_argument("--concurrency", type=int)

    load = subs.add_parser("loadtest", help="Run a bounded local simulation.")
    load.add_argument("--config", required=True)
    load.add_argument("--volume", type=int, default=20)
    load.add_argument("--concurrency", type=int)
    load.add_argument("--recipient")
    load.add_argument("--scenario", choices=sorted(SMS_SCENARIOS), default="success")
    load.add_argument("--report", required=True)

    burst = subs.add_parser(
        "mock-burst",
        help="Simulate a bounded burst against an in-process rate limiter; sends no SMS.",
    )
    burst.add_argument("--attempts", type=int, default=10)
    burst.add_argument("--limit", type=int, default=2)
    burst.add_argument("--window-seconds", type=int, default=60)
    burst.add_argument("--report", required=True)
    return parser


def _show_summary(report):
    summary = report["summary"]
    print(
        f"SMSLab mock run: {summary['total']} cases; {summary['passed']} passed; "
        f"{summary['failed']} failed; {summary['delivered']} simulated deliveries."
    )
    print(f"Elapsed: {summary['duration_ms']} ms; simulated throughput: {summary['throughput_per_s']} cases/s.")


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "init":
            target = Path(args.output)
            if target.exists() and not args.force:
                print(f"ERROR: {target} exists; use --force to overwrite.", file=sys.stderr)
                return 2
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(json.dumps(EXAMPLE_CONFIG, indent=2) + "\n", encoding="utf-8")
            print(f"Config written: {target}")
            return 0

        if args.command == "validate-phone":
            invalid = False
            for value in args.numbers:
                try:
                    print(f"{value} -> {normalize_indian_mobile(value)} (format valid)")
                except PhoneNumberError as exc:
                    print(f"{value} -> INVALID: {exc}", file=sys.stderr)
                    invalid = True
            return 1 if invalid else 0

        if args.command == "scenarios":
            print("SMS scenarios:")
            for key, expected in sorted(SMS_SCENARIOS.items()):
                print(f"  {key}: expected outcome {expected}")
            if args.verbose:
                print("OTP scenarios:")
                for key, expected in (("success", "verified"), ("wrong_code", "wrong_code"), ("expired", "expired"), ("lockout", "locked")):
                    print(f"  {key}: expected outcome {expected}")
            return 0

        if args.command == "mock-burst":
            report = simulate_burst(
                attempts=args.attempts,
                limit=args.limit,
                window_seconds=args.window_seconds,
            )
            write_burst_report(report, args.report)
            summary = report["summary"]
            print(
                f"Mock burst complete: {summary['attempted']} attempts; "
                f"{summary['accepted_by_mock_limiter']} accepted by mock limiter; "
                f"{summary['rejected_rate_limit']} rate-limited; 0 SMS sent."
            )
            print(f"Report written: {args.report}")
            return 0

        config = load_config(args.config)
        if args.command == "validate":
            print(
                f"Config OK: transport=mock, cases={len(config.cases)}, "
                f"recipients={len(config.test_recipients)}, concurrency cap={config.limits.concurrency}"
            )
            return 0

        concurrency = args.concurrency if args.concurrency is not None else config.limits.concurrency
        max_workers = min(config.limits.concurrency, MAX_CONCURRENCY)
        if isinstance(concurrency, bool) or not 1 <= concurrency <= max_workers:
            raise ConfigError(f"Concurrency must be between 1 and {max_workers}.")

        if args.command == "run":
            report = run_cases(config, concurrency=concurrency)
        else:
            max_volume = min(config.limits.max_requests, MAX_REQUESTS)
            if isinstance(args.volume, bool) or not 1 <= args.volume <= max_volume:
                raise ConfigError(f"Volume must be between 1 and {max_volume}.")
            recipient = normalize_indian_mobile(args.recipient) if args.recipient else config.test_recipients[0]
            if recipient not in config.test_recipients:
                raise ConfigError("Requested recipient is not in the test_recipients allowlist.")
            expected = SMS_SCENARIOS[args.scenario]
            load_cases = [
                TestCase(f"load_{i + 1:04d}", "sms", recipient, args.scenario, expected)
                for i in range(args.volume)
            ]
            report = run_cases(config, load_cases, concurrency=concurrency)

        write_report(report, args.report)
        _show_summary(report)
        return 0 if report["summary"]["failed"] == 0 else 1
    except (ConfigError, PhoneNumberError, ValueError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
