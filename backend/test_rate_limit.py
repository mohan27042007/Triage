"""Unit tests for the process-local request limiter; no app/database import."""

import unittest

from rate_limit import RateLimiter


class RateLimiterTests(unittest.TestCase):
    def test_blocks_after_limit_then_recovers_after_window(self):
        limiter = RateLimiter()
        self.assertTrue(limiter.allow("login:ip", 2, 60, now=0))
        self.assertTrue(limiter.allow("login:ip", 2, 60, now=10))
        self.assertFalse(limiter.allow("login:ip", 2, 60, now=20))
        self.assertTrue(limiter.allow("login:ip", 2, 60, now=61))

    def test_keys_are_independent(self):
        limiter = RateLimiter()
        self.assertTrue(limiter.allow("a", 1, 60, now=0))
        self.assertFalse(limiter.allow("a", 1, 60, now=1))
        self.assertTrue(limiter.allow("b", 1, 60, now=1))


if __name__ == "__main__":
    unittest.main()
