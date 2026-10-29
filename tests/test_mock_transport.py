"""Tests for smslab.transports.mock — MockTransport scenario behaviour."""

import unittest

from smslab.transports.mock import MockTransport
from smslab.transports.provider_base import ProviderTransport


class TestMockTransportSuccess(unittest.TestCase):

    def setUp(self):
        self.transport = MockTransport(seed=42)

    def test_success_returns_delivered(self):
        result = self.transport.send("+919999999999", "Hello", timeout_ms=3000, scenario="success")
        self.assertEqual(result.status, "delivered")

    def test_success_has_message_id(self):
        result = self.transport.send("+919999999999", "Hello", timeout_ms=3000, scenario="success")
        self.assertIsNotNone(result.provider_message_id)
        self.assertTrue(result.provider_message_id.startswith("mock-"))

    def test_success_no_error_type(self):
        result = self.transport.send("+919999999999", "Hello", timeout_ms=3000, scenario="success")
        self.assertIsNone(result.error_type)

    def test_success_latency_in_range(self):
        result = self.transport.send("+919999999999", "Hello", timeout_ms=3000, scenario="success")
        self.assertGreaterEqual(result.latency_ms, 20)
        self.assertLessEqual(result.latency_ms, 120)


class TestMockTransportTransientFailure(unittest.TestCase):

    def test_first_attempt_fails(self):
        transport = MockTransport(seed=42)
        result = transport.send("+919999999999", "Hello", timeout_ms=3000, scenario="transient_failure")
        self.assertEqual(result.status, "failed")
        self.assertEqual(result.error_type, "TransientFailure")

    def test_second_attempt_succeeds(self):
        transport = MockTransport(seed=42)
        # First attempt
        transport.send("+919999999999", "Hello", timeout_ms=3000, scenario="transient_failure")
        # Second attempt (same recipient)
        result = transport.send("+919999999999", "Hello", timeout_ms=3000, scenario="transient_failure")
        self.assertEqual(result.status, "delivered")

    def test_attempt_tracking_is_per_recipient(self):
        """Different recipients each start at attempt 0."""
        transport = MockTransport(seed=42)
        # First attempt on recipient A fails
        r1 = transport.send("+919999999999", "Hi", timeout_ms=3000, scenario="transient_failure")
        self.assertEqual(r1.error_type, "TransientFailure")
        # First attempt on recipient B also fails (independent counter)
        r2 = transport.send("+918888888888", "Hi", timeout_ms=3000, scenario="transient_failure")
        self.assertEqual(r2.error_type, "TransientFailure")

    def test_reset_clears_attempt_counts(self):
        transport = MockTransport(seed=42)
        # Exhaust first attempt for +919999999999
        transport.send("+919999999999", "Hi", timeout_ms=3000, scenario="transient_failure")
        transport.reset()
        # After reset, first attempt fails again
        result = transport.send("+919999999999", "Hi", timeout_ms=3000, scenario="transient_failure")
        self.assertEqual(result.error_type, "TransientFailure")


class TestMockTransportPermanentFailure(unittest.TestCase):

    def test_permanent_failure_always_fails(self):
        transport = MockTransport(seed=42)
        for _ in range(3):
            result = transport.send(
                "+919999999999", "Hello", timeout_ms=3000, scenario="permanent_failure"
            )
            self.assertEqual(result.status, "failed")
            self.assertEqual(result.error_type, "PermanentFailure")

    def test_no_message_id_on_failure(self):
        transport = MockTransport(seed=42)
        result = transport.send("+919999999999", "Hello", timeout_ms=3000, scenario="permanent_failure")
        self.assertIsNone(result.provider_message_id)


class TestMockTransportRateLimited(unittest.TestCase):

    def test_rate_limited_returns_failed(self):
        transport = MockTransport(seed=42)
        result = transport.send("+919999999999", "Hello", timeout_ms=3000, scenario="rate_limited")
        self.assertEqual(result.status, "failed")
        self.assertEqual(result.error_type, "RateLimited")

    def test_rate_limited_has_retry_after(self):
        transport = MockTransport(seed=42)
        result = transport.send("+919999999999", "Hello", timeout_ms=3000, scenario="rate_limited")
        self.assertIsNotNone(result.retry_after_ms)
        self.assertGreater(result.retry_after_ms, 0)


class TestMockTransportTimeout(unittest.TestCase):

    def test_timeout_latency_exceeds_timeout_ms(self):
        """Timeout scenario reports latency > timeout_ms."""
        transport = MockTransport(seed=42)
        timeout_ms = 500
        result = transport.send("+919999999999", "Hello", timeout_ms=timeout_ms, scenario="timeout")
        self.assertGreater(result.latency_ms, timeout_ms)
        self.assertEqual(result.error_type, "Timeout")


class TestMockTransportUnknownScenario(unittest.TestCase):

    def test_unknown_scenario_raises_value_error(self):
        transport = MockTransport(seed=42)
        with self.assertRaises(ValueError) as ctx:
            transport.send("+919999999999", "Hi", timeout_ms=3000, scenario="nonexistent_scenario")
        self.assertIn("nonexistent_scenario", str(ctx.exception))


class TestMockTransportDeterminism(unittest.TestCase):

    def test_same_seed_produces_same_results(self):
        """Two transports with the same seed and same calls produce identical results."""
        t1 = MockTransport(seed=99)
        t2 = MockTransport(seed=99)
        r1 = t1.send("+919876543210", "Hi", timeout_ms=3000, scenario="success")
        r2 = t2.send("+919876543210", "Hi", timeout_ms=3000, scenario="success")
        self.assertEqual(r1.latency_ms, r2.latency_ms)

    def test_different_seeds_produce_different_latency(self):
        """Different seeds should produce different random values (with high probability)."""
        t1 = MockTransport(seed=1)
        t2 = MockTransport(seed=2)
        latencies = set()
        for _ in range(5):
            r1 = t1.send("+919876543210", "Hi", timeout_ms=3000, scenario="success")
            r2 = t2.send("+919876543210", "Hi", timeout_ms=3000, scenario="success")
            latencies.add(r1.latency_ms)
            latencies.add(r2.latency_ms)
        # With 10 samples there should be at least 2 distinct values
        self.assertGreater(len(latencies), 1)


class TestProviderTransportStub(unittest.TestCase):

    def test_provider_raises_not_implemented(self):
        """ProviderTransport.send() must always raise NotImplementedError."""
        pt = ProviderTransport()
        with self.assertRaises(NotImplementedError) as ctx:
            pt.send("+919999999999", "Hello", timeout_ms=3000)
        self.assertIn("mock-only", str(ctx.exception).lower())

    def test_provider_error_message_mentions_v1(self):
        pt = ProviderTransport()
        try:
            pt.send("+919999999999", "Hi", timeout_ms=1000)
        except NotImplementedError as exc:
            self.assertIn("v1", str(exc).lower())


if __name__ == "__main__":
    unittest.main()
