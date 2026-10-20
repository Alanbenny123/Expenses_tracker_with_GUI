"""Focused tests that load app logic without optional UI/database packages."""

import ast
import hashlib
import secrets
import unittest
from contextlib import contextmanager
from datetime import date
from hmac import compare_digest
from pathlib import Path
from types import SimpleNamespace


SOURCE = Path(__file__).resolve().parents[1] / "app.py"
FUNCTIONS = {
    "authenticate_pin", "request_pin_reset", "reset_pin",
    "update_user_expense", "delete_user_expenses", "rename_user_category",
    "remove_user_category", "save_user_expense", "get_user_data",
}
tree = ast.parse(SOURCE.read_text())
module = ast.Module(body=[node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in FUNCTIONS], type_ignores=[])
scope = {"text": lambda sql: sql, "hashlib": hashlib, "secrets": secrets, "compare_digest": compare_digest}
exec(compile(module, str(SOURCE), "exec"), scope)


class Result:
    def __init__(self, value=None, rowcount=1):
        self.value = value
        self.rowcount = rowcount

    def one_or_none(self):
        return self.value

    def scalar_one_or_none(self):
        return self.value

    def scalar_one(self):
        return self.value

    def __iter__(self):
        return iter(self.value)


class FakeEngine:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.calls = []

    @contextmanager
    def begin(self):
        yield self

    def execute(self, sql, params):
        self.calls.append((" ".join(sql.split()), params))
        return next(self.responses, Result())


class SecurityAndPersistenceTests(unittest.TestCase):
    def setUp(self):
        self.engine = FakeEngine([])
        scope["get_engine"] = lambda: self.engine
        scope["st"] = SimpleNamespace(error=lambda message: self.fail(message))

    def test_pin_login_targets_one_account_and_locks_after_five_failures(self):
        row = SimpleNamespace(id=7, pin_hash="stored", failed_attempts=4,
                              is_locked=False, lock_expired=False)
        self.engine = FakeEngine([Result(row), Result()])
        scope["verify_pin"] = lambda pin, stored: False
        self.assertIsNone(scope["authenticate_pin"](7, "0000"))
        self.assertIn("WHERE id = :account_id", self.engine.calls[0][0])
        self.assertEqual(self.engine.calls[1][1]["attempts"], 5)

    def test_recovery_email_failure_never_changes_or_reveals_pin(self):
        self.engine = FakeEngine([Result(7), Result(), Result()])
        scope["send_recovery_email"] = lambda *args: (False, "Email unavailable")
        self.assertFalse(scope["request_pin_reset"](7, "person@example.com"))
        self.assertEqual(len(self.engine.calls), 3)
        self.assertTrue(all("pin_hash =" not in sql for sql, _ in self.engine.calls))
        self.assertIn("pin_reset_token_hash = NULL", self.engine.calls[-1][0])

    def test_reset_code_is_single_use_and_account_scoped(self):
        code = "a-random-reset-code"
        token_hash = hashlib.sha256(code.encode()).hexdigest()
        self.engine = FakeEngine([Result(SimpleNamespace(token_valid=True, pin_reset_token_hash=token_hash)), Result()])
        scope["hash_pin"] = lambda pin: "hashed:" + pin
        self.assertTrue(scope["reset_pin"](7, "person@example.com", code, "123456"))
        self.assertIn("WHERE id = :id AND recovery_email = :email", self.engine.calls[0][0])
        self.assertIn("pin_reset_token_hash = NULL", self.engine.calls[1][0])
        self.assertEqual(self.engine.calls[1][1]["pin_hash"], "hashed:123456")

    def test_expense_mutations_require_user_and_expense_ids(self):
        self.engine = FakeEngine([Result(rowcount=1), Result(rowcount=1)])
        expense = {"id": 9, "amount": 12, "description": "Lunch", "category": "food", "date": "2026-10-21"}
        self.assertTrue(scope["update_user_expense"](7, expense))
        self.assertTrue(scope["delete_user_expenses"](7, [9]))
        for sql, params in self.engine.calls:
            self.assertIn("user_id = :user_id", sql)
            self.assertEqual(params["user_id"], 7)
            self.assertEqual(params["id"], 9)

    def test_saved_and_loaded_expenses_keep_database_id(self):
        self.engine = FakeEngine([
            Result(9),
            Result([(9, 12, "Lunch", "food", date(2026, 10, 21))]),
            Result([]),
        ])
        expense = {"amount": 12, "description": "Lunch", "category": "food", "date": "2026-10-21"}
        self.assertEqual(scope["save_user_expense"](7, expense), 9)
        loaded, _ = scope["get_user_data"](7)
        self.assertEqual(loaded[0]["id"], 9)
        self.assertEqual(loaded[0]["date"], "2026-10-21")

    def test_category_mutations_are_user_scoped(self):
        self.engine = FakeEngine([Result(rowcount=1), Result(), Result(rowcount=1)])
        self.assertTrue(scope["rename_user_category"](7, "old", "new"))
        self.assertTrue(scope["remove_user_category"](7, "new"))
        self.assertEqual(len(self.engine.calls), 3)
        self.assertTrue(all("user_id = :user_id" in sql for sql, _ in self.engine.calls))


if __name__ == "__main__":
    unittest.main()
