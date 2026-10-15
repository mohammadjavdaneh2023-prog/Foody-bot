from __future__ import annotations

import unittest
from contextlib import nullcontext
from unittest.mock import Mock

from app.db import Database


class _Result:
    def __init__(self, row: dict[str, int]):
        self.row = row

    def fetchone(self):
        return self.row


class _Cursor:
    def __init__(self):
        self.calls: list[tuple[str, list[tuple]]] = []

    def executemany(self, query: str, params: list[tuple]) -> None:
        self.calls.append((query, params))


class _Connection:
    def __init__(self):
        self.cursor_instance = _Cursor()
        self.results = iter([_Result({"position": 0}), _Result({"id": 42})])

    def execute(self, _query: str, _params: tuple):
        return next(self.results)

    def cursor(self):
        return nullcontext(self.cursor_instance)

    def transaction(self):
        return nullcontext()


class _Pool:
    def __init__(self, connection: _Connection):
        self.connection_instance = connection

    def connection(self):
        return nullcontext(self.connection_instance)


class DatabaseBatchTests(unittest.TestCase):
    def test_batched_profiles_keep_rules_and_replies_with_their_owners(self):
        conn = Mock()
        tables = [
            [
                {
                    "id": pid,
                    "name": str(pid),
                    "mode": "ON",
                    "cooldown_seconds": 0,
                    "delay_min_seconds": 0,
                    "delay_max_seconds": 0,
                }
                for pid in (1, 2)
            ],
            [{"id": 10, "profile_id": 1}, {"id": 11, "profile_id": 1}, {"id": 20, "profile_id": 2}],
            [{"group_id": 10, "normalized_term": "food"}, {"group_id": 20, "normalized_term": "other"}],
            [{"profile_id": 2, "normalized_term": "exclude"}],
            [{"profile_id": 1, "text": "reply1"}, {"profile_id": 2, "text": "reply2"}],
            [{"profile_id": 2, "weekday": 1, "start_minute": 100, "end_minute": 200}],
        ]
        conn.execute.side_effect = [Mock(fetchall=Mock(return_value=rows)) for rows in tables]
        db = Database.__new__(Database)
        db.pool = Mock(connection=Mock(return_value=nullcontext(conn)))
        first, second = db.profiles()
        self.assertEqual(first.rule_groups, [["food"], []])
        self.assertEqual(second.rule_groups, [["other"]])
        self.assertEqual(first.not_terms, [])
        self.assertEqual(second.not_terms, ["exclude"])
        self.assertEqual(first.replies, ["reply1"])
        self.assertEqual(second.replies, ["reply2"])
        self.assertEqual(first.windows, [])
        self.assertEqual(second.windows[0].start_minute, 100)
        self.assertEqual(conn.execute.call_count, 6)

    def setUp(self):
        self.connection = _Connection()
        self.db = Database.__new__(Database)
        self.db.pool = _Pool(self.connection)

    def test_add_group_uses_cursor_executemany(self):
        self.db.add_group(7, ["عباسپور", "دانشگاه عباسپور"])

        query, params = self.connection.cursor_instance.calls[0]
        self.assertIn("INSERT INTO rule_terms", query)
        self.assertEqual(params, [(42, "عباسپور", "عباسپور"), (42, "دانشگاه عباسپور", "دانشگاه عباسپور")])

    def test_add_not_terms_uses_cursor_executemany(self):
        self.db.add_not_terms(7, ["واگذار شد"])

        query, params = self.connection.cursor_instance.calls[0]
        self.assertIn("INSERT INTO not_terms", query)
        self.assertEqual(params, [(7, "واگذار شد", "واگذار شد")])


if __name__ == "__main__":
    unittest.main()
