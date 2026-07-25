"""Focused tests for date-only durable reminder scheduling."""

from datetime import date
import unittest

from reminder_schedule import parse_deadline, reminder_window


class ReminderScheduleTests(unittest.TestCase):
    def test_only_explicit_dates_are_parsed(self):
        today = date(2026, 7, 25)
        self.assertEqual(parse_deadline("2026-07-26", today), date(2026, 7, 26))
        self.assertEqual(parse_deadline("July 26, 2026", today), date(2026, 7, 26))
        self.assertIsNone(parse_deadline("by tomorrow", today))

    def test_yearless_date_rolls_forward_and_windows_are_limited(self):
        today = date(2026, 12, 31)
        self.assertEqual(parse_deadline("January 1", today), date(2027, 1, 1))
        self.assertEqual(reminder_window(date(2027, 1, 1), today), "tomorrow")
        self.assertEqual(reminder_window(today, today), "today")
        self.assertIsNone(reminder_window(date(2026, 12, 29), today))
        self.assertIsNone(reminder_window(date(2027, 1, 3), today))


if __name__ == "__main__":
    unittest.main()
