from __future__ import annotations

import unittest
from contextlib import nullcontext

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
