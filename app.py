import json
import os
from datetime import datetime, timedelta
import pandas as pd
import streamlit as st

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
    """Load expenses from JSON file"""
    if os.path.exists('expenses.json'):
        with open('expenses.json', 'r') as file:
            data = json.load(file)
            st.session_state.expenses = data.get('expenses', [])
            st.session_state.custom_categories = data.get('custom_categories', {})

def save_data():
    """Save expenses to JSON file"""
    with open('expenses.json', 'w') as file:
        data = {
            'expenses': st.session_state.expenses,
            'custom_categories': st.session_state.custom_categories
        }
        json.dump(data, file)

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
                    st.session_state.custom_categories[new_category.strip().lower()] = 0
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
                    st.session_state.custom_categories[cat_name] = 0
                    save_data()
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
                        st.session_state.custom_categories[new_name_lower] = st.session_state.custom_categories.pop(selected)
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

def export_to_excel():
    """Export expenses to Excel"""
    if not st.session_state.expenses:
        st.warning("No expenses to export")
        return
    
    df = pd.DataFrame(st.session_state.expenses)
    excel_data = df.to_excel(index=False, engine='openpyxl')
    
    st.download_button(
        label="📥 Download Excel File",
        data=excel_data if isinstance(excel_data, bytes) else None,
        file_name=f"expenses_{datetime.now().strftime('%Y%m%d')}.xlsx",
        mime="application/vnd.openpyxl.formats-officedocument.spreadsheetml.sheet"
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
        ["➕ Add Expense", "📊 View Summary", "📅 View by Period", "📁 Manage Categories"],
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

