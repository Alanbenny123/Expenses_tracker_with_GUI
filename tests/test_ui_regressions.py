"""Exercise UI decisions without requiring Streamlit or a display server."""

import ast
import json
import math
import os
import re
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]


def load_functions(path, names, globals_):
    tree = ast.parse(path.read_text())
    module = ast.Module(
        body=[node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in names],
        type_ignores=[],
    )
    exec(compile(module, str(path), "exec"), globals_)
    return globals_


class Rerun(Exception):
    pass


class State(dict):
    def __getattr__(self, key):
        return self[key]

    def __setattr__(self, key, value):
        self[key] = value

    def __delattr__(self, key):
        del self[key]


class FakeStreamlit:
    def __init__(self):
        self.session_state = State(
            auth_mode="guest", user_id=None, custom_categories={},
            expenses=[{"amount": 12.0, "description": "Old", "category": "groceries", "date": "2026-10-21"}],
        )
        self.clicked = set()
        self.description = "New"
        self.messages = []

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def columns(self, count):
        return [self] * (len(count) if isinstance(count, list) else count)

    def tabs(self, labels):
        return [self] * len(labels)

    def selectbox(self, *args, **kwargs):
        return "groceries"

    def number_input(self, *args, **kwargs):
        return 12.0

    def text_input(self, label, **kwargs):
        return "2026-10-21" if "Date" in label else self.description

    def button(self, label, **kwargs):
        return label in self.clicked

    def rerun(self):
        raise Rerun()

    def __getattr__(self, name):
        if name == "divider":
            return lambda: None
        if name in {"subheader", "warning", "write", "success", "error", "info", "title", "markdown"}:
            return lambda message: self.messages.append((name, message))
        raise AttributeError(name)


class FakeAccountStreamlit(FakeStreamlit):
    def __init__(self):
        super().__init__()
        self.inputs = {}

    def text_input(self, label, **kwargs):
        return self.inputs.get(kwargs.get("key"), "")


class FakeDataFrame:
    def __init__(self, rows):
        self.index = range(len(rows))
        self.str = self

    def __getitem__(self, key):
        return self

    def __setitem__(self, key, value):
        pass

    def apply(self, function):
        return self

    def capitalize(self):
        return self

    def copy(self):
        return self


class FakeEditStreamlit(FakeStreamlit):
    def __init__(self):
        super().__init__()
        self.amount = 0.0
        self.category_options = None

    def dataframe(self, *args, **kwargs):
        pass

    def number_input(self, label, **kwargs):
        return self.amount if label == "Amount (₹)" else 0

    def selectbox(self, label, options, **kwargs):
        self.category_options = options
        return options[kwargs["index"]]


class UiRegressionTests(unittest.TestCase):
    def setUp(self):
        self.st = FakeStreamlit()
        self.web = {"st": self.st}
        load_functions(ROOT / "app.py", {"add_expense"}, self.web)
        self.web["get_all_categories"] = lambda: {"groceries": 0}
        self.web["parse_date_input"] = lambda value: value
        self.web["record_expense"] = self.record_expense

    def record_expense(self, expense):
        self.st.session_state.expenses.append(expense)
        return True

    def test_duplicate_confirmation_survives_streamlit_rerun(self):
        self.st.clicked = {"💾 Add Expense"}
        with self.assertRaises(Rerun):
            self.web["add_expense"]()
        self.assertEqual(len(self.st.session_state.expenses), 1)
        self.assertIn("pending_duplicate", self.st.session_state)

        self.st.clicked = {"✅ Add Anyway"}
        with self.assertRaises(Rerun):
            self.web["add_expense"]()
        self.assertEqual(len(self.st.session_state.expenses), 2)
        self.assertNotIn("pending_duplicate", self.st.session_state)

    def test_changing_form_discards_pending_duplicate(self):
        self.st.clicked = {"💾 Add Expense"}
        with self.assertRaises(Rerun):
            self.web["add_expense"]()
        self.st.description = "Changed"
        self.st.clicked = {"✅ Add Anyway"}
        self.web["add_expense"]()
        self.assertEqual(len(self.st.session_state.expenses), 1)
        self.assertNotIn("pending_duplicate", self.st.session_state)

    def test_desktop_empty_summary_and_window_exit(self):
        events = []
        desktop = {
            "expenses": [],
            "messagebox": SimpleNamespace(showinfo=lambda *args, **kwargs: events.append("empty-summary")),
            "root": SimpleNamespace(destroy=lambda: events.append("destroy")),
            "se": lambda: events.append("save"),
            "ete": lambda: events.append("export"),
        }
        load_functions(ROOT / "Expenses_tracker_with_GUI", {"vs", "on_exit"}, desktop)
        desktop["vs"]()
        desktop["on_exit"]()
        self.assertEqual(events, ["empty-summary", "save", "destroy"])
        events.clear()
        desktop["on_exit"](export=True)
        self.assertEqual(events, ["save", "export", "destroy"])

    def test_desktop_save_failure_keeps_window_open_and_reports_error(self):
        events = []
        def fail_save():
            raise OSError("disk full")
        desktop = {
            "se": fail_save,
            "ete": lambda: events.append("export"),
            "root": SimpleNamespace(destroy=lambda: events.append("destroy")),
            "messagebox": SimpleNamespace(showerror=lambda *args, **kwargs: events.append(args)),
        }
        load_functions(ROOT / "Expenses_tracker_with_GUI", {"on_exit"}, desktop)
        desktop["on_exit"](export=True)
        self.assertEqual(len(events), 1)
        self.assertIn("disk full", events[0][1])

    def test_desktop_rejects_nonpositive_and_nonfinite_amounts(self):
        for amount in ("0", "-5", "nan", "inf"):
            with self.subTest(amount=amount):
                errors = []
                desktop = {
                    "math": math,
                    "expenses": [],
                    "root": object(),
                    "cc": lambda: "groceries",
                    "ask_string_input": lambda *args: amount,
                    "messagebox": SimpleNamespace(showerror=lambda *args, **kwargs: errors.append(args)),
                }
                load_functions(ROOT / "Expenses_tracker_with_GUI", {"am"}, desktop)
                desktop["am"]()
                self.assertEqual(desktop["expenses"], [])
                self.assertEqual(len(errors), 1)

    def test_desktop_rejects_out_of_range_category_choices(self):
        for action, selection in ((2, 0), (3, -1), (3, 2)):
            with self.subTest(action=action, selection=selection):
                choices = iter((action, selection, None))
                errors = []
                desktop = {
                    "categories": {"groceries": 0},
                    "custom_categories": {"food": 0},
                    "root": object(),
                    "ask_integer_input": lambda *args: next(choices),
                    "ask_string_input": lambda *args: self.fail("Invalid selection reached rename input"),
                    "messagebox": SimpleNamespace(
                        showerror=lambda *args, **kwargs: errors.append(args),
                        showinfo=lambda *args, **kwargs: None,
                    ),
                }
                load_functions(ROOT / "Expenses_tracker_with_GUI", {"manage_categories"}, desktop)
                desktop["manage_categories"]()
                self.assertEqual(desktop["custom_categories"], {"food": 0})
                self.assertEqual(len(errors), 1)

    def test_desktop_category_rename_updates_existing_expenses(self):
        choices = iter((2, 1, None))
        desktop = {
            "categories": {"groceries": 0},
            "custom_categories": {"food": 0},
            "expenses": [
                {"category": "food", "amount": 12},
                {"category": "groceries", "amount": 5},
            ],
            "root": object(),
            "ask_integer_input": lambda *args: next(choices),
            "ask_string_input": lambda *args: " dining ",
            "messagebox": SimpleNamespace(showerror=lambda *args, **kwargs: None,
                                          showinfo=lambda *args, **kwargs: None),
        }
        load_functions(ROOT / "Expenses_tracker_with_GUI", {"manage_categories"}, desktop)
        desktop["manage_categories"]()
        self.assertEqual(desktop["custom_categories"], {"dining": 0})
        self.assertEqual([item["category"] for item in desktop["expenses"]],
                         ["dining", "groceries"])

    def test_web_edit_preserves_removed_category_and_rejects_zero_amount(self):
        fake = FakeEditStreamlit()
        fake.session_state.expenses[0]["category"] = "former"
        fake.clicked = {"💾 Save Changes"}
        edits = {"st": fake, "pd": SimpleNamespace(DataFrame=FakeDataFrame),
                 "math": math, "get_all_categories": lambda: {"groceries": 0},
                 "parse_date_input": lambda value: value,
                 "invalidate_duplicate_selection": lambda: None}
        load_functions(ROOT / "app.py", {"edit_expenses"}, edits)
        edits["edit_expenses"]()
        self.assertEqual(fake.category_options, ["groceries", "former"])
        self.assertEqual(fake.session_state.expenses[0]["amount"], 12.0)
        self.assertIn(("error", "Amount must be a finite number greater than zero"), fake.messages)

        fake.amount = 20.0
        with self.assertRaises(Rerun):
            edits["edit_expenses"]()
        self.assertEqual(fake.session_state.expenses[0]["category"], "former")
        self.assertEqual(fake.session_state.expenses[0]["amount"], 20.0)

    def test_account_screen_registers_and_logs_in(self):
        for action in ("➕ Create Account", "🔑 Login"):
            with self.subTest(action=action):
                fake = FakeAccountStreamlit()
                fake.clicked = {action}
                fake.inputs = {
                    "login_email": "person@example.com", "login_password": "long-password",
                    "new_email": "person@example.com", "new_password": "long-password",
                    "confirm_password": "long-password",
                }
                sessions = []
                account = {
                    "st": fake, "re": re, "get_engine": lambda: object(),
                    "create_account_user": lambda email, password: 17,
                    "authenticate_account": lambda email, password: 17,
                    "start_authenticated_session": lambda user_id: sessions.append(user_id),
                }
                load_functions(ROOT / "app.py", {"show_account_login"}, account)
                with self.assertRaises(Rerun):
                    account["show_account_login"]()
                self.assertEqual(sessions, [17])

    def test_account_password_recovery_uses_email_code(self):
        fake = FakeAccountStreamlit()
        requests = []
        resets = []
        account = {
            "st": fake, "re": re, "get_engine": lambda: object(),
            "request_password_reset": lambda email: requests.append(email),
            "reset_account_password": lambda email, code, password: resets.append((email, code, password)) or True,
        }
        load_functions(ROOT / "app.py", {"show_account_login"}, account)
        fake.clicked = {"Forgot password?"}
        with self.assertRaises(Rerun):
            account["show_account_login"]()
        fake.inputs = {
            "password_reset_email": "person@example.com",
            "password_reset_code": "email-code",
            "reset_account_password": "new-password",
            "confirm_reset_account_password": "new-password",
        }
        fake.clicked = {"Email password reset code"}
        account["show_account_login"]()
        self.assertEqual(requests, ["person@example.com"])
        fake.clicked = {"Set new password"}
        account["show_account_login"]()
        self.assertEqual(resets, [("person@example.com", "email-code", "new-password")])
        self.assertFalse(fake.session_state.show_forgot_password)

    def test_desktop_data_path_is_stable_across_working_directories(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            app_dir = os.path.join(temp_dir, "app")
            old_dir = os.path.join(temp_dir, "old")
            other_dir = os.path.join(temp_dir, "other")
            for path in (app_dir, old_dir, other_dir):
                os.mkdir(path)
            data_file = os.path.join(app_dir, "expenses.json")
            with open(os.path.join(old_dir, "expenses.json"), "w", encoding="utf-8") as file:
                json.dump({"expenses": [{"amount": 12}], "custom_categories": {"food": 0}}, file)
            desktop = {"os": os, "json": json, "tempfile": tempfile, "DATA_FILE": data_file,
                       "expenses": [], "custom_categories": {}}
            load_functions(ROOT / "Expenses_tracker_with_GUI", {"le", "se"}, desktop)
            previous_dir = os.getcwd()
            try:
                os.chdir(old_dir)
                desktop["le"]()
                self.assertEqual(desktop["expenses"], [{"amount": 12}])
                desktop["se"]()
                self.assertTrue(os.path.isfile(data_file))
                desktop["expenses"] = []
                os.chdir(other_dir)
                desktop["le"]()
                self.assertEqual(desktop["expenses"], [{"amount": 12}])
            finally:
                os.chdir(previous_dir)

    def test_desktop_failed_save_preserves_existing_json(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            data_file = os.path.join(temp_dir, "expenses.json")
            with open(data_file, "w", encoding="utf-8") as file:
                json.dump({"expenses": [{"amount": 12}], "custom_categories": {}}, file)
            desktop = {"os": os, "json": json, "tempfile": tempfile,
                       "DATA_FILE": data_file, "expenses": [{"amount": object()}],
                       "custom_categories": {}}
            load_functions(ROOT / "Expenses_tracker_with_GUI", {"se"}, desktop)
            with self.assertRaises(TypeError):
                desktop["se"]()
            with open(data_file, "r", encoding="utf-8") as file:
                self.assertEqual(json.load(file)["expenses"], [{"amount": 12}])
            self.assertEqual(os.listdir(temp_dir), ["expenses.json"])

            desktop["expenses"] = [{"amount": 20}]
            with patch.object(os, "replace", side_effect=OSError("disk error")):
                with self.assertRaises(OSError):
                    desktop["se"]()
            with open(data_file, "r", encoding="utf-8") as file:
                self.assertEqual(json.load(file)["expenses"], [{"amount": 12}])
            self.assertEqual(os.listdir(temp_dir), ["expenses.json"])

    def test_devcontainer_keeps_streamlit_browser_protections(self):
        config = (ROOT / ".devcontainer" / "devcontainer.json").read_text()
        self.assertIn('"server": "streamlit run app.py"', config)
        self.assertNotIn("--server.enableCORS false", config)
        self.assertNotIn("--server.enableXsrfProtection false", config)

    def test_reset_credentials_invalidates_existing_session(self):
        fake = FakeStreamlit()
        fake.session_state.auth_mode = "authenticated"
        fake.session_state.user_id = 17
        fake.session_state.auth_version = 0
        fake.session_state.db_initialized = True
        cleared = []
        app = {
            "st": fake, "get_engine": lambda: object(),
            "get_user_auth_version": lambda user_id: 1,
            "clear_authenticated_session": lambda: cleared.append(True),
        }
        load_functions(ROOT / "app.py", {"main"}, app)
        with self.assertRaises(Rerun):
            app["main"]()
        self.assertEqual(cleared, [True])

    def test_guest_expenses_return_after_authenticated_logout(self):
        fake = FakeStreamlit()
        fake.clicked = {"🔑 Login"}
        fake.session_state.expenses = [{"amount": 12, "category": "groceries"}]
        fake.session_state.custom_categories = {"food": 0}
        app = {"st": fake, "load_data": lambda: None}
        load_functions(ROOT / "app.py", {"main", "clear_authenticated_session",
                                         "invalidate_duplicate_selection"}, app)
        with self.assertRaises(Rerun):
            app["main"]()
        self.assertEqual(fake.session_state.saved_guest_expenses, [{"amount": 12, "category": "groceries"}])

        fake.session_state.auth_mode = "authenticated"
        fake.session_state.user_id = 17
        fake.session_state.expenses = [{"amount": 99, "category": "utilities"}]
        fake.session_state.custom_categories = {"other": 0}
        app["clear_authenticated_session"]()
        self.assertEqual(fake.session_state.expenses, [{"amount": 12, "category": "groceries"}])
        self.assertEqual(fake.session_state.custom_categories, {"food": 0})
        self.assertNotIn("saved_guest_expenses", fake.session_state)


if __name__ == "__main__":
    unittest.main()
