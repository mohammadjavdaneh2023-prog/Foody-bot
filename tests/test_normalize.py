import unittest

from app.normalize import normalize_text


class NormalizeTests(unittest.TestCase):
    def test_persian_letters(self):
        self.assertEqual(normalize_text("ي ك"), "ی ک")

    def test_spaces_and_zwnj(self):
        self.assertEqual(normalize_text("  می\u200cخوام\u00a0  غذا "), "میخوام غذا")

    def test_hashtag(self):
        self.assertEqual(normalize_text("#واگذاری"), "#واگذاری")

    def test_mikhaham_variants(self):
        self.assertEqual(normalize_text("میخوام"), normalize_text("می‌خوام"))
