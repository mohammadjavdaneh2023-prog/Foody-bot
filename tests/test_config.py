from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from app.config import Config


class ConfigTests(unittest.TestCase):
    values = {
        "APP_ENV": "test",
        "APP_VERSION": "test-version",
        "DATABASE_URL": "postgresql://user:pass@localhost/foody_test",
        "TG_API_ID": "12345",
        "TG_API_HASH": "not-a-real-secret",
        "TG_STRING_SESSION": "not-a-real-session",
        "CONTROL_BOT_TOKEN": "not-a-real-token",
        "CONTROL_ADMIN_ID": "123456",
        "TARGET_CHAT_ID": "-100123456",
    }

    def test_required_runtime_configuration(self):
        with patch.dict(os.environ, self.values, clear=True):
            config = Config.from_env()
        self.assertEqual(config.app_version, "test-version")
        self.assertEqual(config.timezone_name, "Asia/Tehran")
        self.assertEqual(config.port, 8080)

    def test_missing_values_are_reported_by_name_not_value(self):
        values = self.values | {"TG_API_HASH": ""}
        with patch.dict(os.environ, values, clear=True), self.assertRaisesRegex(ValueError, "TG_API_HASH"):
            Config.from_env()
