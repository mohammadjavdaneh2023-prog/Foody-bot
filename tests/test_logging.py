from __future__ import annotations

import json
import logging
import os
import unittest
from unittest.mock import patch

from app.logging_setup import JsonFormatter


class LoggingTests(unittest.TestCase):
    def test_secrets_and_phone_like_numbers_are_redacted(self):
        record = logging.LogRecord(
            "test",
            logging.INFO,
            __file__,
            1,
            "failed with secret-value for +989121234567",
            (),
            None,
        )
        with patch.dict(os.environ, {"TG_API_HASH": "secret-value"}, clear=False):
            payload = json.loads(JsonFormatter().format(record))
        self.assertNotIn("secret-value", payload["message"])
        self.assertNotIn("989121234567", payload["message"])
