"""Exercise UI decisions without requiring Streamlit or a display server."""

import ast
import math
import re
import unittest
from pathlib import Path
from types import SimpleNamespace


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
        if name in {"subheader", "warning", "write", "success", "error", "info", "title", "markdown"}:
            return lambda message: self.messages.append((name, message))
        raise AttributeError(name)


class FakeAccountStreamlit(FakeStreamlit):
    def __init__(self):
        super().__init__()
        self.inputs = {}

    def text_input(self, label, **kwargs):
        return self.inputs.get(kwargs.get("key"), "")


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


if __name__ == "__main__":
    unittest.main()
