import unittest

from app.models import Profile
from app.normalize import normalize_text
from app.rules import profile_matches


def p(groups, not_terms=()):
    return Profile(
        1,
        "p",
        "ON",
        0,
        0,
        0,
        [[normalize_text(x) for x in g] for g in groups],
        [normalize_text(x) for x in not_terms],
    )


class RuleTests(unittest.TestCase):
    def test_and_or(self):
        self.assertTrue(
            profile_matches(
                p([["#واگذاری"], ["عباسپور", "دانشگاه عباسپور"], ["پسران", "برادران"]]),
                "#واگذاری دانشگاه عباسپور سلف پسران",
            )
        )

    def test_missing_and(self):
        self.assertFalse(profile_matches(p([["#واگذاری"], ["پسران"]]), "#واگذاری دختران"))

    def test_not(self):
        self.assertFalse(profile_matches(p([["عباسپور"]], ["واگذار شد"]), "عباسپور واگذار شد"))

    def test_empty(self):
        self.assertFalse(profile_matches(p([]), "anything"))

    def test_normalized(self):
        self.assertTrue(profile_matches(p([["دانشگاه عباسپور"]]), "دانشگاه  عباسپور"))
