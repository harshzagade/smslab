"""
smslab.cli — Command-line interface for SMSLab.

Entry point: smslab.cli:main (registered as console script 'smslab').

Subcommands:
  init            — Write example config to a path
  validate        — Validate a config file
  validate-phone  — Normalise and validate Indian mobile numbers
  run             — Execute test cases and write a JSON report
  scenarios       — List supported mock scenarios
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import List, Optional

__all__ = ["main", "build_parser"]

# ---------------------------------------------------------------------------
# Embedded example config (same content as examples/config.example.json)
# ---------------------------------------------------------------------------

_EXAMPLE_CONFIG = """{
  "transport": "mock",
  "seed": 42,
  "limits": {
    "max_cases": 20,
    "concurrency": 4,
    "timeout_ms": 3000
  },
  "test_recipients": [
    "+919999999999",
    "+918888888888",
    "+917777777777"
  ],
  "cases": [
    {
      "name": "sms_success",
      "kind": "sms",
      "recipient": "+919999999999",
      "body": "Hello from SMSLab! Your account is active.",
      "scenario": "success",
      "expected": "delivered"
    },
    {
      "name": "sms_transient_failure",
      "kind": "sms",
      "recipient": "+918888888888",
      "body": "Transient failure test — should succeed on retry.",
      "scenario": "transient_failure",
      "expected": "delivered"
    },
    {
      "name": "sms_permanent_failure",
      "kind": "sms",
      "recipient": "+917777777777",
      "body": "Permanent failure test — landline / DND number.",
      "scenario": "permanent_failure",
      "expected": "failed"
    },
    {
      "name": "sms_rate_limited",
      "kind": "sms",
      "recipient": "+919999999999",
      "body": "Rate limit test — provider returns 429.",
      "scenario": "rate_limited",
      "expected": "failed"
    },
    {
      "name": "sms_timeout",
      "kind": "sms",
      "recipient": "+918888888888",
      "body": "Timeout test — simulated latency exceeds timeout_ms.",
      "scenario": "timeout",
      "expected": "failed"
    },
    {
      "name": "otp_success",
      "kind": "otp",
      "recipient": "+917777777777",
      "scenario": "success",
      "expected": "verified"
    }
  ]
}
"""


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    """Build and return the top-level argument parser."""
    parser = argparse.ArgumentParser(
        prog="smslab",
        description=(
            "SMSLab — Mock-first SMS/OTP integration testing CLI.\n"
            "No real SMS is ever sent. Transport is always 'mock'."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    subparsers = parser.add_subparsers(dest="subcommand", metavar="SUBCOMMAND")

    # --- init ---
    init_parser = subparsers.add_parser(
        "init",
        help="Write the example config to a file.",
        description="Scaffold an example SMSLab config file at the specified path.",
    )
    init_parser.add_argument(
        "--output",
        required=True,
        metavar="PATH",
        help="Destination path for the config file.",
    )
    init_parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite PATH if it already exists.",
    )

    # --- validate ---
    validate_parser = subparsers.add_parser(
        "validate",
        help="Load and validate a config file.",
        description="Validate a SMSLab JSON config file and report any errors.",
    )
    validate_parser.add_argument(
        "--config",
        required=True,
        metavar="PATH",
        help="Path to the config JSON file.",
    )

    # --- validate-phone ---
    vphone_parser = subparsers.add_parser(
        "validate-phone",
        help="Normalise and validate Indian mobile number(s).",
        description=(
            "Validate one or more phone numbers as Indian mobile numbers.\n"
            "Accepted formats: +91XXXXXXXXXX, 91XXXXXXXXXX, 0XXXXXXXXXX, XXXXXXXXXX."
        ),
    )
    vphone_parser.add_argument(
        "numbers",
        nargs="+",
        metavar="NUMBER",
        help="One or more phone numbers to validate.",
    )

    # --- run ---
    run_parser = subparsers.add_parser(
        "run",
        help="Run test cases and write a JSON report.",
        description="Execute all test cases defined in the config and write results.",
    )
    run_parser.add_argument(
        "--config",
        required=True,
        metavar="PATH",
        help="Path to the config JSON file.",
    )
    run_parser.add_argument(
        "--report",
        required=True,
        metavar="PATH",
        help="Output path for the JSON report file.",
    )
    run_parser.add_argument(
        "--log",
        metavar="PATH",
        default=None,
        help="Optional path to write structured JSON log lines.",
    )
    run_parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress per-case progress output.",
    )

    # --- scenarios ---
    subparsers.add_parser(
        "scenarios",
        help="List all supported mock scenarios.",
        description="Print the list of supported SMS/OTP scenarios with descriptions.",
    )

    return parser


# ---------------------------------------------------------------------------
# Subcommand handlers
# ---------------------------------------------------------------------------


def _cmd_init(args: argparse.Namespace) -> int:
    """Handle: smslab init --output PATH [--force]"""
    output = Path(args.output)
    if output.exists() and not args.force:
        print(
            f"Error: {output} already exists. Use --force to overwrite.",
            file=sys.stderr,
        )
        return 2

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(_EXAMPLE_CONFIG, encoding="utf-8")
    print(f"Config written to: {output}")
    print(
        "Next steps:\n"
        f"  smslab validate --config {output}\n"
        f"  smslab run --config {output} --report report.json"
    )
    return 0


def _cmd_validate(args: argparse.Namespace) -> int:
    """Handle: smslab validate --config PATH"""
    from smslab.config import ConfigError, load_config

    config_path = Path(args.config)
    if not config_path.exists():
        print(
            f"Error: config file not found: {config_path}",
            file=sys.stderr,
        )
        return 2

    try:
        cfg = load_config(config_path)
    except ConfigError as exc:
        print(f"Config error: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:  # noqa: BLE001
        print(f"Unexpected error: {exc}", file=sys.stderr)
        return 2

    print(
        f"Config OK: {len(cfg.cases)} cases, "
        f"{len(cfg.test_recipients)} test recipients, "
        f"transport={cfg.transport}"
    )
    return 0


def _cmd_validate_phone(args: argparse.Namespace) -> int:
    """Handle: smslab validate-phone NUMBER [NUMBER ...]"""
    from smslab.phones import PhoneValidationError, normalize_indian

    exit_code = 0
    for raw in args.numbers:
        try:
            normalised = normalize_indian(raw)
            print(f"{raw} -> {normalised} (valid Indian mobile)")
        except PhoneValidationError as exc:
            print(f"{raw} -> ERROR: {exc}", file=sys.stderr)
            exit_code = 2
    return exit_code


def _cmd_run(args: argparse.Namespace) -> int:
    """Handle: smslab run --config PATH --report PATH [--log PATH] [--quiet]"""
    from smslab.config import ConfigError, load_config
    from smslab.report import render_text_summary, report_to_json
    from smslab.runner import run_cases

    config_path = Path(args.config)
    report_path = Path(args.report)

    if not config_path.exists():
        print(
            f"Error: config file not found: {config_path}",
            file=sys.stderr,
        )
        return 2

    try:
        cfg = load_config(config_path)
    except ConfigError as exc:
        print(f"Config error: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:  # noqa: BLE001
        print(f"Unexpected error loading config: {exc}", file=sys.stderr)
        return 2

    if not args.quiet:
        print(
            f"SMSLab run: {len(cfg.cases)} cases, "
            f"concurrency={cfg.limits.concurrency}, "
            f"seed={cfg.seed}"
        )
        print()

    try:
        report = run_cases(cfg, log_path=args.log, quiet=args.quiet)
    except Exception as exc:  # noqa: BLE001
        print(f"Run error: {exc}", file=sys.stderr)
        return 2

    # Write report file
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(report_to_json(report), encoding="utf-8")

    # Print text summary
    if not args.quiet:
        print(render_text_summary(report))
    else:
        s = report.summary
        print(
            f"Done: {s.passed}/{s.total} passed, "
            f"{s.failed} failed, "
            f"{s.duration_ms}ms"
        )

    print(f"Report written to: {report_path}")

    # Exit 0 if all pass, 1 if any fail
    return 0 if report.summary.failed == 0 else 1


def _cmd_scenarios(_args: argparse.Namespace) -> int:
    """Handle: smslab scenarios"""
    from smslab.transports.mock import SUPPORTED_SCENARIOS

    print("Supported SMSLab scenarios:")
    print()
    for name, description in sorted(SUPPORTED_SCENARIOS.items()):
        print(f"  {name:<22s}  {description}")
    print()
    print("Use 'scenario' field in each case config to select one of the above.")
    return 0


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main(argv: Optional[List[str]] = None) -> None:
    """Main entry point for the 'smslab' console script."""
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.subcommand is None:
        parser.print_help()
        sys.exit(2)

    handlers = {
        "init": _cmd_init,
        "validate": _cmd_validate,
        "validate-phone": _cmd_validate_phone,
        "run": _cmd_run,
        "scenarios": _cmd_scenarios,
    }

    handler = handlers.get(args.subcommand)
    if handler is None:  # pragma: no cover
        parser.print_help()
        sys.exit(2)

    exit_code = handler(args)
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
