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
    "hash_pin", "hash_password", "verify_password", "create_account_user", "authenticate_account",
    "request_password_reset", "reset_account_password",
    "get_user_auth_version", "send_account_ids_by_email", "create_pin_user",
    "init_db",
}
tree = ast.parse(SOURCE.read_text())
module = ast.Module(body=[node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in FUNCTIONS], type_ignores=[])
scope = {"text": lambda sql: sql, "hashlib": hashlib, "secrets": secrets, "compare_digest": compare_digest}
exec(compile(module, str(SOURCE), "exec"), scope)
ORIGINAL_FUNCTIONS = {name: scope[name] for name in FUNCTIONS}


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

    def fetchone(self):
        return (self.value,)

    def scalars(self):
        return self

    def all(self):
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

    def execute(self, sql, params=None):
        self.calls.append((" ".join(sql.split()), params))
        return next(self.responses, Result())


class SecurityAndPersistenceTests(unittest.TestCase):
    def setUp(self):
        scope.update(ORIGINAL_FUNCTIONS)
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
        self.assertIn("WHERE id = :id AND LOWER(TRIM(recovery_email)) = :email", self.engine.calls[0][0])
        self.assertIn("pin_reset_token_hash = NULL", self.engine.calls[1][0])
        self.assertIn("auth_version = auth_version + 1", self.engine.calls[1][0])
        self.assertEqual(self.engine.calls[1][1]["pin_hash"], "hashed:123456")

    def test_pin_recovery_email_is_case_and_whitespace_insensitive(self):
        self.engine = FakeEngine([Result(7)])
        self.assertEqual(scope["create_pin_user"]("1234", " Person@Example.COM "), 7)
        self.assertEqual(self.engine.calls[0][1]["recovery_email"], "person@example.com")

        self.engine = FakeEngine([Result([7])])
        sent = []
        scope["send_recovery_email"] = lambda email, *args: sent.append(email) or (True, "sent")
        self.assertTrue(scope["send_account_ids_by_email"](" PERSON@example.com "))
        self.assertEqual(self.engine.calls[0][1]["email"], "person@example.com")
        self.assertIn("LOWER(TRIM(recovery_email)) = :email", self.engine.calls[0][0])
        self.assertEqual(sent, ["person@example.com"])

        self.engine = FakeEngine([Result(7), Result()])
        self.assertTrue(scope["request_pin_reset"](7, " PERSON@example.com "))
        self.assertEqual(self.engine.calls[0][1]["email"], "person@example.com")

        code = "case-insensitive-code"
        token_hash = hashlib.sha256(code.encode()).hexdigest()
        self.engine = FakeEngine([Result(SimpleNamespace(token_valid=True, pin_reset_token_hash=token_hash)), Result()])
        self.assertTrue(scope["reset_pin"](7, " PERSON@example.com ", code, "1234"))
        self.assertEqual(self.engine.calls[0][1]["email"], "person@example.com")

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

    def test_account_registration_hashes_password_and_normalizes_email(self):
        self.engine = FakeEngine([Result(17)])
        self.assertEqual(scope["create_account_user"](" Person@Example.COM ", "long-password"), 17)
        params = self.engine.calls[0][1]
        self.assertEqual(params["email"], "person@example.com")
        self.assertNotEqual(params["password_hash"], "long-password")
        self.assertTrue(scope["verify_password"]("long-password", params["password_hash"]))
        self.assertFalse(scope["verify_password"]("wrong-password", params["password_hash"]))

    def test_account_login_is_email_scoped_and_locks_after_five_failures(self):
        password_hash = scope["hash_password"]("long-password")
        row = SimpleNamespace(id=17, password_hash=password_hash, failed_attempts=4,
                              is_locked=False, lock_expired=False)
        self.engine = FakeEngine([Result(row), Result()])
        self.assertIsNone(scope["authenticate_account"]("PERSON@EXAMPLE.COM", "wrong-password"))
        self.assertIn("email = :email AND user_type = 'account'", self.engine.calls[0][0])
        self.assertEqual(self.engine.calls[0][1]["email"], "person@example.com")
        self.assertEqual(self.engine.calls[1][1]["attempts"], 5)

    def test_account_login_accepts_correct_password(self):
        password_hash = scope["hash_password"]("long-password")
        row = SimpleNamespace(id=17, password_hash=password_hash, failed_attempts=2,
                              is_locked=False, lock_expired=False)
        self.engine = FakeEngine([Result(row), Result()])
        self.assertEqual(scope["authenticate_account"]("person@example.com", "long-password"), 17)
        self.assertIn("failed_attempts = 0", self.engine.calls[1][0])

    def test_password_reset_request_does_not_change_password_when_email_fails(self):
        self.engine = FakeEngine([Result(17), Result(), Result()])
        scope["send_recovery_email"] = lambda *args: (False, "Email unavailable")
        self.assertFalse(scope["request_password_reset"]("Person@Example.COM"))
        self.assertEqual(self.engine.calls[0][1]["email"], "person@example.com")
        self.assertTrue(all("password_hash =" not in sql for sql, _ in self.engine.calls))
        self.assertIn("password_reset_token_hash = NULL", self.engine.calls[-1][0])

    def test_password_reset_request_does_not_reveal_unknown_email(self):
        self.engine = FakeEngine([Result(None)])
        sent = []
        scope["send_recovery_email"] = lambda *args: sent.append(args)
        self.assertTrue(scope["request_password_reset"]("unknown@example.com"))
        self.assertEqual(sent, [])
        self.assertEqual(len(self.engine.calls), 1)

    def test_password_reset_requires_valid_code_and_consumes_it(self):
        code = "random-email-code"
        code_hash = hashlib.sha256(code.encode()).hexdigest()
        row = SimpleNamespace(id=17, password_reset_token_hash=code_hash, token_valid=True)
        scope["hash_password"] = lambda password: "hashed:" + password
        self.engine = FakeEngine([Result(row)])
        self.assertFalse(scope["reset_account_password"]("person@example.com", "wrong", "new-password"))
        self.assertEqual(len(self.engine.calls), 1)
        self.engine = FakeEngine([Result(row), Result()])
        self.assertTrue(scope["reset_account_password"]("PERSON@EXAMPLE.COM", code, "new-password"))
        self.assertEqual(self.engine.calls[0][1]["email"], "person@example.com")
        self.assertEqual(self.engine.calls[1][1]["password_hash"], "hashed:new-password")
        self.assertIn("password_reset_token_hash = NULL", self.engine.calls[1][0])
        self.assertIn("auth_version = auth_version + 1", self.engine.calls[1][0])

    def test_expired_password_reset_code_cannot_change_password(self):
        row = SimpleNamespace(id=17, password_reset_token_hash="stored", token_valid=False)
        self.engine = FakeEngine([Result(row)])
        self.assertFalse(scope["reset_account_password"]("person@example.com", "any-code", "new-password"))
        self.assertEqual(len(self.engine.calls), 1)

    def test_auth_version_is_loaded_for_session_revocation(self):
        self.engine = FakeEngine([Result(3)])
        self.assertEqual(scope["get_user_auth_version"](17), 3)
        self.assertEqual(self.engine.calls[0][1]["user_id"], 17)

    def test_legacy_database_tables_gain_account_scoped_columns_and_index(self):
        scope["init_db"]()
        statements = [sql for sql, _ in self.engine.calls]
        expense_table = next(i for i, sql in enumerate(statements) if "CREATE TABLE IF NOT EXISTS expenses" in sql)
        expense_owner = next(i for i, sql in enumerate(statements) if "ALTER TABLE expenses ADD COLUMN" in sql)
        category_table = next(i for i, sql in enumerate(statements) if "CREATE TABLE IF NOT EXISTS custom_categories" in sql)
        category_owner = next(i for i, sql in enumerate(statements) if "ALTER TABLE custom_categories ADD COLUMN" in sql)
        drop_global_unique = next(i for i, sql in enumerate(statements) if "DROP CONSTRAINT IF EXISTS custom_categories_name_key" in sql)
        scoped_unique = next(i for i, sql in enumerate(statements) if "CREATE UNIQUE INDEX IF NOT EXISTS custom_categories_user_id_name_key" in sql)
        self.assertLess(expense_table, expense_owner)
        self.assertLess(category_table, category_owner)
        self.assertLess(category_owner, drop_global_unique)
        self.assertLess(drop_global_unique, scoped_unique)
        self.assertIn("REFERENCES users(id) ON DELETE CASCADE", statements[expense_owner])
        self.assertIn("ON custom_categories(user_id, name)", statements[scoped_unique])


if __name__ == "__main__":
    unittest.main()
