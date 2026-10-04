import unittest
from datetime import datetime

from app.models import Profile, ScheduleWindow
from app.scheduler import is_profile_active, parse_delay_range, parse_window


def p(mode, windows=()):
    return Profile(1, "p", mode, 0, 0, 0, windows=list(windows))


class ScheduleTests(unittest.TestCase):
    def setUp(self):
        self.monday = datetime(2026, 1, 5, 10, 30)

    def test_modes(self):
        self.assertFalse(is_profile_active(p("OFF"), self.monday))
        self.assertTrue(is_profile_active(p("ON"), self.monday))

    def test_boundaries(self):
        profile = p("SCHEDULE", [ScheduleWindow(0, 630, 810)])
        self.assertTrue(is_profile_active(profile, self.monday))
        self.assertFalse(is_profile_active(profile, self.monday.replace(hour=13, minute=30)))

    def test_weekday_and_multiple(self):
        profile = p("SCHEDULE", [ScheduleWindow(1, 0, 60), ScheduleWindow(0, 1000, 1100)])
        self.assertFalse(is_profile_active(profile, self.monday))
        self.assertTrue(is_profile_active(profile, self.monday.replace(hour=17)))

    def test_parse_rejects_overnight(self):
        with self.assertRaises(ValueError):
            parse_window("23:00-01:00")

    def test_delay_range(self):
        self.assertEqual(parse_delay_range("2-10"), (2, 10))
        self.assertEqual(parse_delay_range("0-0"), (0, 0))
        with self.assertRaises(ValueError):
            parse_delay_range("10-2")
