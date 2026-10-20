"""Exercise UI decisions without requiring Streamlit or a display server."""

import ast
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
        return [self] * count

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
        if name in {"subheader", "warning", "write", "success", "error", "info"}:
            return lambda message: self.messages.append((name, message))
        raise AttributeError(name)


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


if __name__ == "__main__":
    unittest.main()
