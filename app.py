import json
import os
from datetime import datetime, timedelta
import pandas as pd
import streamlit as st
from io import BytesIO

# Load environment variables from .env when available (for local dev)
try:
    from dotenv import load_dotenv

    load_dotenv()
except Exception:
    pass

# Optional: SQLAlchemy for Postgres persistence when DATABASE_URL is set
try:
    from sqlalchemy import create_engine, text
except Exception:  # library may not be installed in some environments
    create_engine = None
    text = None

# Page config
st.set_page_config(
    page_title="Expense Tracker",
    page_icon="💰",
    layout="centered",
    initial_sidebar_state="collapsed"
)

# Initialize session state
if 'expenses' not in st.session_state:
    st.session_state.expenses = []
if 'custom_categories' not in st.session_state:
    st.session_state.custom_categories = {}

categories = {"groceries": 0, "transportation": 0, "entertainment": 0, "utilities": 0}


# ---------------------------
# Persistence helpers (DB/JSON)
# ---------------------------
def get_engine():
    """Return a cached SQLAlchemy engine if DATABASE_URL is set and SQLAlchemy is available."""
    db_url = os.environ.get("DATABASE_URL")
    if not db_url or create_engine is None:
        return None
    if "db_engine" not in st.session_state:
        st.session_state.db_engine = create_engine(db_url, pool_pre_ping=True)
    return st.session_state.db_engine


def init_db():
    """Create tables if they do not exist (when using DB)."""
    engine = get_engine()
    if engine is None:
        return
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS expenses (
                id SERIAL PRIMARY KEY,
                amount NUMERIC NOT NULL,
                description TEXT,
                category TEXT NOT NULL,
                date DATE NOT NULL
            );
        """))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS custom_categories (
                id SERIAL PRIMARY KEY,
                name TEXT UNIQUE NOT NULL
            );
        """))


def db_load_data():
    """Load data from DB into session state."""
    engine = get_engine()
    if engine is None:
        return False
    init_db()
    with engine.begin() as conn:
        rows = conn.execute(text("SELECT amount, description, category, date FROM expenses ORDER BY date")).mappings().all()
        st.session_state.expenses = [dict(r) for r in rows]
        cat_rows = conn.execute(text("SELECT name FROM custom_categories ORDER BY name")).scalars().all()
        st.session_state.custom_categories = {name: 0 for name in cat_rows}
    return True


def db_add_expense(expense):
    engine = get_engine()
    if engine is None:
        return False
    with engine.begin() as conn:
        conn.execute(
            text("INSERT INTO expenses(amount, description, category, date) VALUES(:a,:d,:c,:dt)"),
            {"a": expense["amount"], "d": expense["description"], "c": expense["category"], "dt": expense["date"]},
        )
    return True


def db_add_category(name):
    engine = get_engine()
    if engine is None:
        return False
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO custom_categories(name) VALUES(:n) ON CONFLICT (name) DO NOTHING"), {"n": name})
    return True


def db_rename_category(old_name, new_name):
    engine = get_engine()
    if engine is None:
        return False
    with engine.begin() as conn:
        conn.execute(text("UPDATE custom_categories SET name=:new WHERE name=:old"), {"new": new_name, "old": old_name})
        # Update existing expense rows to use the new category name
        conn.execute(text("UPDATE expenses SET category=:new WHERE category=:old"), {"new": new_name, "old": old_name})
    return True


def db_remove_category(name):
    engine = get_engine()
    if engine is None:
        return False
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM custom_categories WHERE name=:n"), {"n": name})
    return True


def db_update_expense(index, expense):
    """Update expense by index (requires loading expenses first to get the correct ID)"""
    engine = get_engine()
    if engine is None:
        return False
    
    # Get all expenses to find the correct database ID for this index
    with engine.begin() as conn:
        rows = conn.execute(text("SELECT id FROM expenses ORDER BY date")).fetchall()
        if index >= len(rows):
            return False
        
        expense_id = rows[index][0]
        conn.execute(
            text("UPDATE expenses SET amount=:a, description=:d, category=:c, date=:dt WHERE id=:id"),
            {
                "a": expense["amount"],
                "d": expense["description"], 
                "c": expense["category"],
                "dt": expense["date"],
                "id": expense_id
            }
        )
    return True


def db_delete_expense(index):
    """Delete expense by index (requires loading expenses first to get the correct ID)"""
    engine = get_engine()
    if engine is None:
        return False
    
    # Get all expenses to find the correct database ID for this index
    with engine.begin() as conn:
        rows = conn.execute(text("SELECT id FROM expenses ORDER BY date")).fetchall()
        if index >= len(rows):
            return False
        
        expense_id = rows[index][0]
        conn.execute(text("DELETE FROM expenses WHERE id=:id"), {"id": expense_id})
    return True


def parse_date_input(date_input):
    """Parse flexible date input formats and convert to YYYY-MM-DD"""
    if not date_input:
        return None
    
    date_input = str(date_input).strip()
    today = datetime.now()
    
    # If just DD (e.g., "15")
    if date_input.isdigit() and len(date_input) <= 2:
        try:
            day = int(date_input)
            if 1 <= day <= 31:
                year = today.year
                month = today.month
                try:
                    test_date = datetime(year, month, day)
                    return test_date.strftime("%Y-%m-%d")
                except ValueError:
                    return None
        except ValueError:
            pass
    
    parts = str(date_input).split('-')
    
    # If YYYY-MM-DD, normalize and return
    if len(parts) == 3 and len(parts[0]) == 4:
        try:
            year = int(parts[0])
            month = int(parts[1])
            day = int(parts[2])
            datetime(year, month, day)
            return f"{year:04d}-{month:02d}-{day:02d}"
        except (ValueError, IndexError):
            return None
    
    # If YY-MM-DD (e.g., "24-01-15" or "24-1-15")
    if len(parts) == 3 and len(parts[0]) <= 2:
        try:
            year = int(parts[0])
            month = int(parts[1])
            day = int(parts[2])
            full_year = 2000 + year if year < 100 else year
            datetime(full_year, month, day)
            return f"{full_year:04d}-{month:02d}-{day:02d}"
        except (ValueError, IndexError):
            return None
    
    # If MM-DD (e.g., "01-15" or "1-15")
    if len(parts) == 2:
        try:
            month = int(parts[0])
            day = int(parts[1])
            if 1 <= month <= 12 and 1 <= day <= 31:
                year = today.year
                datetime(year, month, day)
                return f"{year:04d}-{month:02d}-{day:02d}"
        except (ValueError, IndexError):
            return None
    
    return None

def load_data():
    """Load expenses from browser localStorage (session-based)"""
    # Initialize from localStorage if available, otherwise start fresh
    if 'expenses' not in st.session_state:
        st.session_state.expenses = []
    if 'custom_categories' not in st.session_state:
        st.session_state.custom_categories = {}

def save_data():
    """Save expenses to browser localStorage (automatic via session state)"""
    # Data is automatically persisted in Streamlit session state
    # Each browser session maintains its own isolated data
    pass

def get_all_categories():
    """Get all categories including custom ones"""
    return {**categories, **st.session_state.custom_categories}

def add_expense():
    """Add expense form"""
    st.subheader("➕ Add Expense")
    
    all_categories = get_all_categories()
    category_list = list(all_categories.keys())
    
    col1, col2 = st.columns(2)
    
    with col1:
        category = st.selectbox(
            "Select Category",
            category_list + ["➕ Add Custom Category"],
            key="add_category"
        )
    
    if category == "➕ Add Custom Category":
        with st.expander("Add Custom Category"):
            new_category = st.text_input("Category Name", key="new_cat_name")
            if st.button("Add Category", key="add_cat_btn"):
                if new_category and new_category.strip().lower() not in get_all_categories():
                    name = new_category.strip().lower()
                    st.session_state.custom_categories[name] = 0
                    save_data()
                    st.success(f"Category '{new_category}' added!")
                    st.rerun()
                elif new_category.strip().lower() in get_all_categories():
                    st.error("Category already exists!")
        return
    
    with col2:
        amount = st.number_input("Amount (₹)", min_value=0.0, step=0.01, key="add_amount")
    
    description = st.text_input("Description", key="add_desc")
    
    date_input = st.text_input(
        "Date (YYYY-MM-DD or DD or YY-MM-DD or MM-DD)",
        placeholder="e.g., 15 or 24-01-15",
        key="add_date"
    )
    
    if st.button("💾 Add Expense", type="primary", use_container_width=True):
        if not date_input:
            st.error("Please enter a date")
            return
        
        parsed_date = parse_date_input(date_input)
        if parsed_date is None:
            try:
                parsed_date = datetime.strptime(date_input, "%Y-%m-%d").strftime("%Y-%m-%d")
            except ValueError:
                st.error("Invalid date format. Use: DD, YY-MM-DD, MM-DD, or YYYY-MM-DD")
                return
        
        expense = {
            'amount': amount,
            'description': description,
            'category': category,
            'date': parsed_date
        }
        
        # Check for duplicates (same date, category, amount, and description)
        # Handle empty descriptions properly
        desc_normalized = description.lower().strip() if description else ""
        duplicates = [
            e for e in st.session_state.expenses 
            if (e['date'] == parsed_date and 
                e['category'] == category and 
                e['amount'] == amount and 
                (e['description'].lower().strip() if e['description'] else "") == desc_normalized)
        ]
        
        if duplicates:
            st.warning(f"⚠️ Found {len(duplicates)} identical expense(s) with the same date, category, amount, and description:")
            for i, dup in enumerate(duplicates[:3], 1):  # Show max 3 duplicates
                st.write(f"{i}. {dup['description']} - ₹{dup['amount']:.2f} on {dup['date']} ({dup['category'].capitalize()})")
            if len(duplicates) > 3:
                st.write(f"... and {len(duplicates) - 3} more")
            
            # Use unique keys with timestamp to avoid conflicts
            import time
            timestamp = str(int(time.time() * 1000))
            
            col1, col2 = st.columns(2)
            with col1:
                if st.button("✅ Add Anyway", type="primary", use_container_width=True, key=f"confirm_add_{timestamp}"):
                    # Add to session state
                    st.session_state.expenses.append(expense)
                    save_data()
                    st.success("✅ Expense added successfully!")
                    st.rerun()
            with col2:
                if st.button("❌ Cancel", use_container_width=True, key=f"cancel_add_{timestamp}"):
                    st.info("Expense not added.")
                    st.rerun()
        else:
            # No duplicates, add directly to session state
            st.session_state.expenses.append(expense)
            save_data()
            st.success("✅ Expense added successfully!")
            st.rerun()

def view_summary():
    """View expense summary"""
    st.subheader("📊 Expense Summary")
    
    if not st.session_state.expenses:
        st.info("No expenses recorded yet.")
        return
    
    total_expense = sum(expense['amount'] for expense in st.session_state.expenses)
    
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Total Expenses", f"₹{total_expense:.2f}")
    with col2:
        st.metric("Total Transactions", len(st.session_state.expenses))
    with col3:
        avg = total_expense / len(st.session_state.expenses) if st.session_state.expenses else 0
        st.metric("Average per Transaction", f"₹{avg:.2f}")
    
    st.divider()
    
    # Expenses by category
    cs = {}
    for expense in st.session_state.expenses:
        cat = expense['category']
        cs[cat] = cs.get(cat, 0) + expense['amount']
    
    if cs:
        st.write("**Expenses by Category:**")
        category_df = pd.DataFrame([
            {'Category': k.capitalize(), 'Amount': v}
            for k, v in sorted(cs.items(), key=lambda x: x[1], reverse=True)
        ])
        st.bar_chart(category_df.set_index('Category'))
        
        st.write("**Category Details:**")
        for category, amount in sorted(cs.items(), key=lambda x: x[1], reverse=True):
            count = sum(1 for e in st.session_state.expenses if e['category'] == category)
            avg = amount / count if count > 0 else 0
            st.write(f"- **{category.capitalize()}**: ₹{amount:.2f} ({count} transactions, avg: ₹{avg:.2f})")
        
        highest = max(cs, key=cs.get)
        lowest = min(cs, key=cs.get)
        st.info(f"💡 Highest: {highest.capitalize()} (₹{cs[highest]:.2f}) | Lowest: {lowest.capitalize()} (₹{cs[lowest]:.2f})")

def view_expenses_period():
    """View expenses by period"""
    st.subheader("📅 View Expenses by Period")
    
    period = st.radio(
        "Select Period",
        ["Daily", "Weekly", "Monthly"],
        horizontal=True
    )
    
    if period == "Daily":
        date_input = st.text_input(
            "Enter date (YYYY-MM-DD or DD or YY-MM-DD or MM-DD)",
            key="daily_date"
        )
        if st.button("View", key="view_daily"):
            if date_input:
                parsed_date = parse_date_input(date_input)
                if parsed_date is None:
                    try:
                        parsed_date = datetime.strptime(date_input, "%Y-%m-%d").strftime("%Y-%m-%d")
                    except ValueError:
                        st.error("Invalid date format")
                        return
                
                fe = [e for e in st.session_state.expenses if e['date'] == parsed_date]
                display_expenses(fe, f"Expenses for {parsed_date}")
            else:
                st.error("Please enter a date")
    
    elif period == "Weekly":
        month_input = st.text_input("Enter month (YYYY-MM)", key="weekly_month")
        if st.button("View", key="view_weekly"):
            if month_input:
                try:
                    som = datetime.strptime(month_input, "%Y-%m").replace(day=1)
                    eom = (som + timedelta(days=31)).replace(day=1) - timedelta(days=1)
                    
                    cws = som
                    wn = 1
                    
                    while cws <= eom:
                        we = cws + timedelta(days=6)
                        if we > eom:
                            we = eom
                        
                        fe = [e for e in st.session_state.expenses 
                              if cws.strftime("%Y-%m-%d") <= e['date'] <= we.strftime("%Y-%m-%d")]
                        if fe:
                            display_expenses(fe, f"Week {wn} ({cws.strftime('%Y-%m-%d')} to {we.strftime('%Y-%m-%d')})")
                        else:
                            st.info(f"No expenses for Week {wn}")
                        
                        cws = we + timedelta(days=1)
                        wn += 1
                except ValueError:
                    st.error("Invalid month format. Use YYYY-MM")
            else:
                st.error("Please enter a month")
    
    elif period == "Monthly":
        month_input = st.text_input("Enter month (YYYY-MM)", key="monthly_month")
        if st.button("View", key="view_monthly"):
            if month_input:
                try:
                    som = datetime.strptime(month_input, "%Y-%m").replace(day=1)
                    eom = (som + timedelta(days=31)).replace(day=1) - timedelta(days=1)
                    
                    fe = [e for e in st.session_state.expenses
                          if som.strftime("%Y-%m-%d") <= e['date'] <= eom.strftime("%Y-%m-%d")]
                    display_expenses(fe, f"Expenses for {month_input}")
                except ValueError:
                    st.error("Invalid month format. Use YYYY-MM")
            else:
                st.error("Please enter a month")

def display_expenses(expenses_list, title="Expenses"):
    """Display expenses in a table"""
    if not expenses_list:
        st.info(f"No expenses found for {title}")
        return
    
    total = sum(e['amount'] for e in expenses_list)
    st.write(f"**{title}** - Total: ₹{total:.2f}")
    
    df = pd.DataFrame(expenses_list)
    df['Amount'] = df['amount'].apply(lambda x: f"₹{x:.2f}")
    df['Category'] = df['category'].str.capitalize()
    df = df[['date', 'Category', 'description', 'Amount']]
    df.columns = ['Date', 'Category', 'Description', 'Amount']
    st.dataframe(df, use_container_width=True, hide_index=True)

def manage_categories():
    """Manage custom categories"""
    st.subheader("📁 Manage Categories")
    
    option = st.selectbox(
        "Choose action",
        ["Add Custom Category", "Edit Custom Category", "Remove Custom Category", "View All Categories"]
    )
    
    if option == "Add Custom Category":
        new_cat = st.text_input("Category Name", key="new_category")
        if st.button("Add", key="add_new_cat"):
            if new_cat:
                cat_name = new_cat.strip().lower()
                if cat_name not in get_all_categories():
                    if not db_add_category(cat_name):
                        st.session_state.custom_categories[cat_name] = 0
                        save_data()
                    else:
                        db_load_data()
                    st.success(f"Category '{cat_name}' added!")
                    st.rerun()
                else:
                    st.error("Category already exists!")
    
    elif option == "Edit Custom Category":
        if not st.session_state.custom_categories:
            st.info("No custom categories to edit.")
        else:
            cat_list = list(st.session_state.custom_categories.keys())
            selected = st.selectbox("Select category to edit", cat_list, key="edit_cat")
            new_name = st.text_input("New name", key="new_cat_name")
            if st.button("Update", key="update_cat"):
                if new_name:
                    new_name_lower = new_name.strip().lower()
                    if new_name_lower not in get_all_categories():
                        # Rename in session state
                        st.session_state.custom_categories[new_name_lower] = st.session_state.custom_categories.pop(selected)
                        # Update existing expenses with the new category name
                        for expense in st.session_state.expenses:
                            if expense['category'] == selected:
                                expense['category'] = new_name_lower
                        save_data()
                        st.success(f"Category renamed to '{new_name_lower}'!")
                        st.rerun()
                    else:
                        st.error("Category name already exists!")
    
    elif option == "Remove Custom Category":
        if not st.session_state.custom_categories:
            st.info("No custom categories to remove.")
        else:
            cat_list = list(st.session_state.custom_categories.keys())
            selected = st.selectbox("Select category to remove", cat_list, key="remove_cat")
            if st.button("Remove", type="primary", key="remove_btn"):
                del st.session_state.custom_categories[selected]
                save_data()
                st.success(f"Category '{selected}' removed!")
                st.rerun()
    
    elif option == "View All Categories":
        all_cats = get_all_categories()
        st.write("**All Categories:**")
        for idx, cat in enumerate(all_cats.keys(), 1):
            st.write(f"{idx}. {cat.capitalize()}")

def edit_expenses():
    """Edit existing expenses"""
    st.subheader("✏️ Edit Expenses")
    
    if not st.session_state.expenses:
        st.info("No expenses to edit.")
        return
    
    # Create a DataFrame for display
    df = pd.DataFrame(st.session_state.expenses)
    df['index'] = df.index
    df['Amount'] = df['amount'].apply(lambda x: f"₹{x:.2f}")
    df['Category'] = df['category'].str.capitalize()
    df['Date'] = df['date']
    df['Description'] = df['description']
    
    display_df = df[['index', 'Date', 'Category', 'Description', 'Amount']].copy()
    display_df.columns = ['#', 'Date', 'Category', 'Description', 'Amount']
    
    st.write("**Select an expense to edit:**")
    st.dataframe(display_df, use_container_width=True, hide_index=True)
    
    # Select expense to edit
    expense_index = st.number_input(
        "Enter expense number (#) to edit:",
        min_value=0,
        max_value=len(st.session_state.expenses) - 1,
        step=1,
        key="edit_expense_index"
    )
    
    if expense_index < len(st.session_state.expenses):
        expense = st.session_state.expenses[expense_index]
        
        st.divider()
        st.write(f"**Editing Expense #{expense_index}**")
        
        col1, col2 = st.columns(2)
        
        with col1:
            # Category selection
            all_categories = get_all_categories()
            category_list = list(all_categories.keys())
            current_category_idx = category_list.index(expense['category']) if expense['category'] in category_list else 0
            
            new_category = st.selectbox(
                "Category",
                category_list,
                index=current_category_idx,
                key="edit_category"
            )
        
        with col2:
            new_amount = st.number_input(
                "Amount (₹)",
                min_value=0.0,
                step=0.01,
                value=float(expense['amount']),
                key="edit_amount"
            )
        
        new_description = st.text_input(
            "Description",
            value=expense['description'],
            key="edit_description"
        )
        
        new_date_input = st.text_input(
            "Date (YYYY-MM-DD or DD or YY-MM-DD or MM-DD)",
            value=expense['date'],
            key="edit_date"
        )
        
        col1, col2, col3 = st.columns(3)
        
        with col1:
            if st.button("💾 Save Changes", type="primary", use_container_width=True):
                # Parse the new date
                parsed_date = parse_date_input(new_date_input)
                if parsed_date is None:
                    try:
                        parsed_date = datetime.strptime(new_date_input, "%Y-%m-%d").strftime("%Y-%m-%d")
                    except ValueError:
                        st.error("Invalid date format")
                        return
                
                # Update the expense
                updated_expense = {
                    'amount': new_amount,
                    'description': new_description,
                    'category': new_category,
                    'date': parsed_date
                }
                
                # Update in session state
                st.session_state.expenses[expense_index] = updated_expense
                save_data()
                st.success("✅ Expense updated successfully!")
                st.rerun()
        
        with col2:
            if st.button("🗑️ Delete Expense", use_container_width=True):
                # Delete from session state
                st.session_state.expenses.pop(expense_index)
                save_data()
                st.success("🗑️ Expense deleted successfully!")
                st.rerun()
        
        with col3:
            if st.button("❌ Cancel", use_container_width=True):
                st.rerun()

def remove_duplicates():
    """Remove duplicate expenses with selective deletion"""
    st.subheader("🧹 Remove Duplicates")
    
    if not st.session_state.expenses:
        st.info("No expenses to check.")
        return
    
    # Find ALL duplicates (including originals)
    duplicate_groups = {}
    
    for i, expense in enumerate(st.session_state.expenses):
        # Create a key for comparison (normalize description)
        desc_normalized = expense['description'].lower().strip() if expense['description'] else ""
        key = (
            expense['date'],
            expense['category'],
            expense['amount'],
            desc_normalized
        )
        
        if key not in duplicate_groups:
            duplicate_groups[key] = []
        duplicate_groups[key].append((i, expense))
    
    # Filter to only groups with duplicates (more than 1 item)
    actual_duplicates = {k: v for k, v in duplicate_groups.items() if len(v) > 1}
    
    if actual_duplicates:
        total_duplicates = sum(len(group) for group in actual_duplicates.values())
        st.warning(f"⚠️ Found {len(actual_duplicates)} duplicate groups with {total_duplicates} total expenses:")
        
        # Initialize selection state
        if 'selected_for_deletion' not in st.session_state:
            st.session_state.selected_for_deletion = set()
        
        # Show each duplicate group
        for group_idx, (key, group) in enumerate(actual_duplicates.items()):
            date, category, amount, description = key
            st.write(f"**Group {group_idx + 1}:** {category.capitalize()} - ₹{amount:.2f} on {date}")
            if description:
                st.write(f"Description: {description}")
            
            # Show all items in this group with checkboxes
            for item_idx, (original_idx, expense) in enumerate(group):
                col1, col2 = st.columns([1, 10])
                with col1:
                    selected = st.checkbox(
                        "",
                        key=f"delete_{original_idx}",
                        value=original_idx in st.session_state.selected_for_deletion
                    )
                    if selected:
                        st.session_state.selected_for_deletion.add(original_idx)
                    elif original_idx in st.session_state.selected_for_deletion:
                        st.session_state.selected_for_deletion.remove(original_idx)
                
                with col2:
                    st.write(f"#{original_idx}: {expense['description']} - ₹{expense['amount']:.2f} on {expense['date']}")
            
            st.divider()
        
        # Action buttons
        col1, col2, col3 = st.columns(3)
        
        with col1:
            if st.button("✅ Select All Duplicates", use_container_width=True):
                # Select all but keep one from each group (keep the first one)
                for group in actual_duplicates.values():
                    for i, (original_idx, _) in enumerate(group):
                        if i > 0:  # Keep first, select rest for deletion
                            st.session_state.selected_for_deletion.add(original_idx)
                st.rerun()
        
        with col2:
            if st.button("❌ Clear Selection", use_container_width=True):
                st.session_state.selected_for_deletion.clear()
                st.rerun()
        
        with col3:
            selected_count = len(st.session_state.selected_for_deletion)
            if selected_count > 0:
                if st.button(f"🗑️ Delete Selected ({selected_count})", type="primary", use_container_width=True):
                    # Remove selected expenses (in reverse order to maintain indices)
                    indices_to_remove = sorted(st.session_state.selected_for_deletion, reverse=True)
                    for idx in indices_to_remove:
                        st.session_state.expenses.pop(idx)
                    
                    st.session_state.selected_for_deletion.clear()
                    save_data()
                    st.success(f"✅ Deleted {selected_count} expense(s)!")
                    st.rerun()
            else:
                st.button("🗑️ Delete Selected (0)", disabled=True, use_container_width=True)
    else:
        st.success("✅ No duplicates found! Your expenses are clean.")

def export_to_excel():
    """Export expenses to Excel"""
    if not st.session_state.expenses:
        st.warning("No expenses to export")
        return
    df = pd.DataFrame(st.session_state.expenses)
    buffer = BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        df.to_excel(writer, index=False)
    buffer.seek(0)
    st.download_button(
        label="📥 Download Excel File",
        data=buffer,
        file_name=f"expenses_{datetime.now().strftime('%Y%m%d')}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )

# Main app
def main():
    # Load data on startup
    load_data()
    
    # Header
    st.title("💰 Expense Tracker")
    st.divider()
    
    # Navigation
    page = st.radio(
        "Navigation",
        ["➕ Add Expense", "📊 View Summary", "📅 View by Period", "✏️ Edit Expenses", "🧹 Remove Duplicates", "📁 Manage Categories"],
        horizontal=True,
        label_visibility="collapsed"
    )
    
    st.divider()
    
    # Page routing
    if page == "➕ Add Expense":
        add_expense()
    elif page == "📊 View Summary":
        view_summary()
    elif page == "📅 View by Period":
        view_expenses_period()
    elif page == "✏️ Edit Expenses":
        edit_expenses()
    elif page == "🧹 Remove Duplicates":
        remove_duplicates()
    elif page == "📁 Manage Categories":
        manage_categories()
    
    # Export option
    st.divider()
    export_to_excel()
    
    # Auto-save indicator
    if st.session_state.expenses:
        st.caption(f"💾 {len(st.session_state.expenses)} expenses saved")

if __name__ == "__main__":
    main()



