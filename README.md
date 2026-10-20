# 💰 Expense Tracker

A comprehensive expense tracking application with both **desktop GUI** and **web app** versions. Track your daily expenses, analyze spending patterns, and manage custom categories with an intuitive interface.

![Python](https://img.shields.io/badge/Python-3.8+-blue.svg)
![License](https://img.shields.io/badge/License-MIT-green.svg)
![Status](https://img.shields.io/badge/Status-Active-success.svg)

## ✨ Features

### Core Functionality
- **➕ Add Expenses** - Record expenses with flexible date input formats
- **📊 View Summary** - Get insights with category-wise breakdowns and statistics
- **📅 Filter by Period** - View expenses by daily, weekly, or monthly periods
- **📁 Custom Categories** - Create and manage your own expense categories
- **💾 Data Persistence** - Desktop data is saved to JSON when the window closes; authenticated web data is stored in PostgreSQL
- **📥 Export to Excel** - Download your expense data as Excel files

### Smart Date Input
Enter dates in multiple formats:
- `15` → Uses current year and month
- `24-01-15` → Automatically converts to 2024-01-15
- `01-15` → Uses current year
- `2024-01-15` → Full date format

### Desktop Version (Tkinter)
- Modern, clean GUI with styled buttons
- Color-coded interface with hover effects
- Centered, responsive dialogs
- Keyboard shortcuts (Enter/Escape)

### Web Version (Streamlit)
- Beautiful, responsive web interface
- Interactive charts and visualizations
- Real-time data updates
- Free hosting on Streamlit Cloud

## 🚀 Quick Start

### Desktop Version

```bash
# Clone the repository
git clone https://github.com/Alanbenny123/Expenses_tracker_with_GUI.git
cd Expenses_tracker_with_GUI

# Install dependencies
pip install pandas openpyxl

# Run the application
python Expenses_tracker_with_GUI
```

### Web Version (Streamlit) – Local Development

```bash
# Install Streamlit dependencies
pip install -r requirements.txt

# (Optional) create a .env file with your Postgres URL for persistent storage
echo DATABASE_URL="postgresql://USER:PASSWORD@HOST/neondb?sslmode=require" > .env

# Run the web app
streamlit run app.py
```

### Configure persistent storage with Neon (optional but recommended)

1. Sign up for the free tier at [neon.tech](https://console.neon.tech)
2. Create a project → choose the closest region (e.g. *Asia Pacific – Singapore* for India)
3. Click **Connect** → select **SQLAlchemy** → copy the connection string  
   `postgresql://USER:PASSWORD@HOST/neondb?sslmode=require`
4. For local dev, place this string in `.env` as shown above (the app loads it via `python-dotenv`)
5. Without `DATABASE_URL`, the web app offers guest mode with session-only data. PIN accounts require PostgreSQL. The desktop app uses `expenses.json`.

### Deploy to Streamlit Community Cloud (free)

1. Push the repo to GitHub
2. Visit [share.streamlit.io](https://share.streamlit.io) and sign in with GitHub
3. Click **New app** → select this repository (`main` branch, `app.py`)
4. Before deploying, open **Advanced settings → Secrets** and add:
   ```
   DATABASE_URL="postgresql://USER:PASSWORD@HOST/neondb?sslmode=require"
   ```
5. Deploy. Streamlit rebuilds automatically whenever you push new commits.
6. Your live app (e.g. `https://trackmyrupees.streamlit.app`) now persists data in Neon Postgres 🎉

## 📋 Requirements

### Desktop Version
- Python 3.8+
- tkinter (usually pre-installed)
- pandas
- openpyxl

### Web Version
- Python 3.8+
- streamlit
- pandas
- openpyxl

## 📖 Usage

### Adding an Expense
1. Select "Add Expense" from the main menu
2. Choose a category (or add a custom one)
3. Enter amount, description, and date
4. Click "Add Expense"

### PIN accounts on the web

Create a PIN account with `DATABASE_URL` configured, then save the Account ID shown after creation. Login requires both the Account ID and PIN. A recovery email is optional; if provided, it can receive your Account ID and a 15-minute PIN reset code. Email recovery requires `GMAIL_USER` and `GMAIL_APP_PASSWORD` to be configured. Accounts without a recovery email need their Account ID to be supplied by the database administrator if it is lost.

### Email/password accounts on the web

With `DATABASE_URL` configured, Account Mode supports registration and login using an email address and a password of at least eight characters. Passwords are stored as salted hashes. Five failed sign-in attempts lock an account for 15 minutes. Password recovery is not available yet, so keep your password safe.

### Viewing Summary
- See total expenses across all categories
- View average spending per category
- Identify highest and lowest spending categories
- Get transaction counts and statistics

### Managing Categories
- Add custom categories on the fly
- Edit existing custom categories
- Remove categories you no longer need
- View all available categories

## 🛠️ Technologies Used

- **Python** - Core programming language
- **Tkinter** - Desktop GUI framework
- **Streamlit** - Web app framework
- **Pandas** - Data manipulation and Excel export
- **JSON** - Data storage format

## 📁 Project Structure

```
Expenses_tracker_with_GUI/
├── Expenses_tracker_with_GUI  # Desktop version (Tkinter)
├── app.py                      # Web version (Streamlit)
├── requirements.txt            # Python dependencies
├── expenses.json               # Data file (auto-created)
├── .gitignore                  # Git ignore rules
└── README.md                   # This file
```

## 🎯 Key Features Explained

### Flexible Date Input
The app intelligently parses various date formats:
- Single digit days → Uses current month/year
- Two-digit years → Auto-converts to 20XX format
- Month-day format → Uses current year
- Full dates → Standard YYYY-MM-DD format

### Category Management
- **Default Categories**: Groceries, Transportation, Entertainment, Utilities
- **Custom Categories**: Add unlimited custom categories
- **Dynamic Updates**: Categories refresh immediately after changes

### Data Export
- Export all expenses to Excel (.xlsx)
- Includes all fields: date, category, description, amount
- Perfect for further analysis in spreadsheet software

## 🔮 Future Enhancements

- [ ] Persistent guest storage or SQLite support
- [ ] Password recovery and email verification for account mode
- [ ] Budget setting and tracking
- [ ] Expense reports and analytics
- [ ] Mobile app version
- [ ] Cloud sync functionality
- [ ] Recurring expense support
- [ ] Receipt image upload

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit your changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

## 📝 License

This project is licensed under the MIT License - see the LICENSE file for details.

## 🙏 Acknowledgments

- Built with Python and love for personal finance management
- UI inspired by modern Material Design principles

## 📞 Support

If you encounter any issues or have questions:
- Open an issue on GitHub
- Check existing issues for solutions

---

**Made with ❤️ for better expense tracking**

⭐ Star this repo if you find it helpful!



