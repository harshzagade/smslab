"""
Safety tests for smslab — banned module scan and structural guarantees.

These tests ensure:
1. No networking modules appear anywhere in the smslab package source.
2. ProviderTransport.send() raises NotImplementedError unconditionally.
3. Config with transport != 'mock' is rejected.
"""

import ast
import os
import unittest
from pathlib import Path

from smslab.transports.provider_base import ProviderTransport


# Modules whose import would allow network access
BANNED_MODULES = frozenset([
    "socket",
    "urllib",
    "http.client",
    "httplib",
    "requests",
    "httpx",
    "aiohttp",
    "boto3",        # AWS SDK
    "twilio",
    "vonage",
])


def _collect_smslab_sources() -> list[Path]:
    """Return all .py files inside the smslab package directory."""
    pkg_root = Path(__file__).parent.parent / "smslab"
    return list(pkg_root.rglob("*.py"))


def _extract_imports(source: str) -> list[str]:
    """Parse Python source and return a list of all imported module names."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []

    imported: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imported.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imported.append(node.module)
    return imported


class TestBannedModuleScan(unittest.TestCase):
    """Scan smslab source files for imports of banned (network) modules."""

    def test_no_banned_module_imported(self):
        """No smslab source file may import any of the banned networking modules."""
        sources = _collect_smslab_sources()
        self.assertGreater(len(sources), 0, "No smslab source files found")

        violations: list[str] = []
        for src_path in sources:
            source_text = src_path.read_text(encoding="utf-8")
            imports = _extract_imports(source_text)
            for imp in imports:
                for banned in BANNED_MODULES:
                    # Check exact match or "socket.something" style
                    if imp == banned or imp.startswith(banned + "."):
                        violations.append(f"{src_path.name}: imports '{imp}' (banned: '{banned}')")

        if violations:
            self.fail(
                "Banned networking module(s) found in smslab package source:\n"
                + "\n".join(f"  {v}" for v in violations)
            )

    def test_scanned_files_include_key_modules(self):
        """Verify scanner covered the key modules (sanity check)."""
        sources = {p.name for p in _collect_smslab_sources()}
        for expected in ["phones.py", "config.py", "runner.py", "otp.py"]:
            self.assertIn(expected, sources, f"Expected source file {expected} not found")

    def test_transport_files_are_scanned(self):
        """Transport modules must also be scanned."""
        sources = {p.name for p in _collect_smslab_sources()}
        for expected in ["mock.py", "base.py", "provider_base.py"]:
            self.assertIn(expected, sources, f"Transport file {expected} not in scan set")


class TestProviderStubSafety(unittest.TestCase):

    def test_provider_send_raises_not_implemented(self):
        """ProviderTransport.send() must always raise NotImplementedError."""
        pt = ProviderTransport()
        with self.assertRaises(NotImplementedError):
            pt.send("+919999999999", "test", timeout_ms=1000)

    def test_provider_error_mentions_mock_only(self):
        """The NotImplementedError message must mention mock-only design."""
        pt = ProviderTransport()
        try:
            pt.send("+919999999999", "test", timeout_ms=1000)
        except NotImplementedError as exc:
            msg = str(exc).lower()
            self.assertIn("mock", msg)

    def test_provider_base_has_no_network_code(self):
        """provider_base.py must not contain any networking imports."""
        pkg_root = Path(__file__).parent.parent / "smslab" / "transports"
        provider_src = (pkg_root / "provider_base.py").read_text(encoding="utf-8")
        imports = _extract_imports(provider_src)
        for imp in imports:
            for banned in BANNED_MODULES:
                self.assertFalse(
                    imp == banned or imp.startswith(banned + "."),
                    f"provider_base.py imports banned module '{imp}'"
                )


class TestTransportEnforcement(unittest.TestCase):
    """Ensure configs with non-mock transports are always rejected."""

    def test_non_mock_transport_rejected(self):
        """load_config() rejects any transport != 'mock'."""
        import json
        import tempfile
        from smslab.config import ConfigError, load_config

        for transport_name in ["twilio", "aws_sns", "vonage", "real", "", "Mock", "MOCK"]:
            with self.subTest(transport=transport_name):
                config = {
                    "transport": transport_name,
                    "seed": 1,
                    "limits": {"max_cases": 1, "concurrency": 1, "timeout_ms": 1000},
                    "test_recipients": ["+919999999999"],
                    "cases": [
                        {
                            "name": "x",
                            "kind": "sms",
                            "recipient": "+919999999999",
                            "body": "hi",
                            "scenario": "success",
                            "expected": "delivered",
                        }
                    ],
                }
                with tempfile.NamedTemporaryFile(
                    mode="w", suffix=".json", delete=False
                ) as f:
                    json.dump(config, f)
                    tmp_path = f.name
                try:
                    with self.assertRaises(ConfigError):
                        load_config(tmp_path)
                finally:
                    os.unlink(tmp_path)


if __name__ == "__main__":
    unittest.main()
