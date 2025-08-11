import sqlite3
import hashlib
import datetime
import shutil
import os

# --- Constants ---
DB_NAME = 'finance_manager.db'
DATE_FORMAT = '%Y-%m-%d'
BACKUP_DIR = 'backups'

# --- Database Manager Class ---
class DBManager:
    """
    Manages all interactions with the SQLite database.
    Handles connection, table creation, and query execution.
    """
    def __init__(self, db_name=DB_NAME):
        self.db_name = db_name
        self.conn = None
        self.cursor = None
        self._connect()
        self._create_tables()

    def _connect(self):
        """Establishes a connection to the SQLite database."""
        try:
            self.conn = sqlite3.connect(self.db_name)
            self.cursor = self.conn.cursor()
            print(f"Connected to database: {self.db_name}")
        except sqlite3.Error as e:
            print(f"Database connection error: {e}")
            exit(1) # Exit if cannot connect to database

    def _execute_query(self, query, params=()):
        """
        Executes a SQL query with optional parameters.
        Commits changes for INSERT, UPDATE, DELETE queries.
        """
        try:
            self.cursor.execute(query, params)
            if query.strip().upper().startswith(('INSERT', 'UPDATE', 'DELETE')):
                self.conn.commit()
            return True
        except sqlite3.Error as e:
            print(f"Database query error: {e}")
            return False

    def _fetch_one(self, query, params=()):
        """Executes a query and fetches a single row."""
        self._execute_query(query, params)
        return self.cursor.fetchone()

    def _fetch_all(self, query, params=()):
        """Executes a query and fetches all rows."""
        self._execute_query(query, params)
        return self.cursor.fetchall()

    def _create_tables(self):
        """Creates necessary tables if they don't exist."""
        # Users table
        self._execute_query("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL
            )
        """)
        # Transactions table (for both income and expenses)
        self._execute_query("""
            CREATE TABLE IF NOT EXISTS transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                type TEXT NOT NULL CHECK(type IN ('income', 'expense')),
                category TEXT NOT NULL,
                amount REAL NOT NULL,
                date TEXT NOT NULL,
                description TEXT,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        """)
        # Budgets table
        self._execute_query("""
            CREATE TABLE IF NOT EXISTS budgets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                category TEXT NOT NULL,
                amount REAL NOT NULL,
                month INTEGER NOT NULL,
                year INTEGER NOT NULL,
                UNIQUE(user_id, category, month, year),
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        """)
        print("Database tables checked/created.")

    def close(self):
        """Closes the database connection."""
        if self.conn:
            self.conn.close()
            print("Database connection closed.")

# --- User Management ---
class UserManager:
    """Handles user registration and authentication."""
    def __init__(self, db_manager):
        self.db = db_manager

    def _hash_password(self, password):
        """Hashes a password using SHA256."""
        return hashlib.sha256(password.encode()).hexdigest()

    def register_user(self, username, password):
        """
        Registers a new user.
        Returns True on success, False if username already exists or error.
        """
        password_hash = self._hash_password(password)
        query = "INSERT INTO users (username, password_hash) VALUES (?, ?)"
        if self.db._execute_query(query, (username, password_hash)):
            print(f"User '{username}' registered successfully.")
            return True
        else:
            print(f"Error: Username '{username}' might already exist or database error.")
            return False

    def authenticate_user(self, username, password):
        """
        Authenticates a user.
        Returns user_id on success, None on failure.
        """
        password_hash = self._hash_password(password)
        query = "SELECT id, password_hash FROM users WHERE username = ?"
        user_data = self.db._fetch_one(query, (username,))

        if user_data and user_data[1] == password_hash:
            print(f"User '{username}' authenticated successfully.")
            return user_data[0] # Return user_id
        else:
            print("Invalid username or password.")
            return None

# --- Transaction Management ---
class TransactionManager:
    """Handles adding, updating, and deleting income/expense entries."""
    def __init__(self, db_manager):
        self.db = db_manager
        self.transaction_types = ['income', 'expense']
        self.categories = {
            'income': ['Salary', 'Freelance', 'Investments', 'Gift', 'Other Income'],
            'expense': ['Food', 'Rent', 'Utilities', 'Transport', 'Entertainment',
                        'Shopping', 'Health', 'Education', 'Other Expense']
        }

    def _validate_date(self, date_str):
        """Validates if a string is a valid date in YYYY-MM-DD format."""
        try:
            datetime.datetime.strptime(date_str, DATE_FORMAT)
            return True
        except ValueError:
            return False

    def add_transaction(self, user_id, trans_type, category, amount, date_str, description=""):
        """Adds a new income or expense transaction."""
        if trans_type not in self.transaction_types:
            print(f"Invalid transaction type. Must be one of: {', '.join(self.transaction_types)}")
            return False
        if category not in self.categories[trans_type]:
            print(f"Invalid category for {trans_type}. Available categories: {', '.join(self.categories[trans_type])}")
            return False
        if not isinstance(amount, (int, float)) or amount <= 0:
            print("Amount must be a positive number.")
            return False
        if not self._validate_date(date_str):
            print(f"Invalid date format. Please use YYYY-MM-DD.")
            return False

        query = "INSERT INTO transactions (user_id, type, category, amount, date, description) VALUES (?, ?, ?, ?, ?, ?)"
        if self.db._execute_query(query, (user_id, trans_type, category, amount, date_str, description)):
            print(f"{trans_type.capitalize()} added successfully.")
            return True
        return False

    def update_transaction(self, user_id, transaction_id, trans_type, category, amount, date_str, description=""):
        """Updates an existing transaction."""
        # First, verify the transaction belongs to the user and exists
        check_query = "SELECT id, type FROM transactions WHERE id = ? AND user_id = ?"
        transaction_data = self.db._fetch_one(check_query, (transaction_id, user_id))

        if not transaction_data:
            print(f"Transaction with ID {transaction_id} not found or does not belong to you.")
            return False

        # Ensure the transaction type matches the original type
        if transaction_data[1] != trans_type:
            print(f"Cannot change transaction type from '{transaction_data[1]}' to '{trans_type}'.")
            return False

        if category not in self.categories[trans_type]:
            print(f"Invalid category for {trans_type}. Available categories: {', '.join(self.categories[trans_type])}")
            return False
        if not isinstance(amount, (int, float)) or amount <= 0:
            print("Amount must be a positive number.")
            return False
        if not self._validate_date(date_str):
            print(f"Invalid date format. Please use YYYY-MM-DD.")
            return False

        query = """
            UPDATE transactions
            SET category = ?, amount = ?, date = ?, description = ?
            WHERE id = ? AND user_id = ?
        """
        if self.db._execute_query(query, (category, amount, date_str, description, transaction_id, user_id)):
            print(f"Transaction ID {transaction_id} updated successfully.")
            return True
        return False

    def delete_transaction(self, user_id, transaction_id):
        """Deletes a transaction."""
        query = "DELETE FROM transactions WHERE id = ? AND user_id = ?"
        if self.db._execute_query(query, (transaction_id, user_id)):
            if self.db.cursor.rowcount > 0:
                print(f"Transaction ID {transaction_id} deleted successfully.")
                return True
            else:
                print(f"Transaction with ID {transaction_id} not found or does not belong to you.")
                return False
        return False

    def get_transactions(self, user_id, trans_type=None, start_date=None, end_date=None):
        """
        Retrieves transactions for a user, optionally filtered by type and date range.
        Returns a list of tuples (id, type, category, amount, date, description).
        """
        query = "SELECT id, type, category, amount, date, description FROM transactions WHERE user_id = ?"
        params = [user_id]

        if trans_type and trans_type in self.transaction_types:
            query += " AND type = ?"
            params.append(trans_type)
        if start_date and self._validate_date(start_date):
            query += " AND date >= ?"
            params.append(start_date)
        if end_date and self._validate_date(end_date):
            query += " AND date <= ?"
            params.append(end_date)

        query += " ORDER BY date DESC"
        return self.db._fetch_all(query, params)

# --- Budgeting ---
class BudgetManager:
    """Handles setting and checking monthly budgets."""
    def __init__(self, db_manager):
        self.db = db_manager
        self.transaction_manager = TransactionManager(db_manager) # For getting expenses

    def set_budget(self, user_id, category, amount, month, year):
        """
        Sets or updates a monthly budget for a specific category.
        Month should be 1-12.
        """
        if category not in self.transaction_manager.categories['expense']:
            print(f"Invalid expense category. Available categories: {', '.join(self.transaction_manager.categories['expense'])}")
            return False
        if not isinstance(amount, (int, float)) or amount < 0:
            print("Budget amount must be a non-negative number.")
            return False
        if not (1 <= month <= 12) or not (year >= 1900 and year <= 2100): # Basic year range
            print("Invalid month (1-12) or year (e.g., 2023).")
            return False

        # Use INSERT OR REPLACE to handle both setting and updating
        query = """
            INSERT OR REPLACE INTO budgets (user_id, category, amount, month, year)
            VALUES (
                (SELECT id FROM users WHERE id = ?), ?, ?, ?, ?
            )
        """
        if self.db._execute_query(query, (user_id, category, amount, month, year)):
            print(f"Budget for {category} in {month}/{year} set to ${amount:.2f}.")
            return True
        return False

    def get_budget(self, user_id, category, month, year):
        """Retrieves the budget for a given category, month, and year."""
        query = "SELECT amount FROM budgets WHERE user_id = ? AND category = ? AND month = ? AND year = ?"
        result = self.db._fetch_one(query, (user_id, category, month, year))
        return result[0] if result else 0.0

    def get_expenses_for_category_in_month(self, user_id, category, month, year):
        """Calculates total expenses for a specific category in a given month."""
        start_date = f"{year}-{month:02d}-01"
        # Calculate end date for the month
        if month == 12:
            end_date = f"{year}-12-31"
        else:
            next_month_date = datetime.date(year, month + 1, 1)
            end_date = (next_month_date - datetime.timedelta(days=1)).strftime(DATE_FORMAT)

        query = """
            SELECT SUM(amount) FROM transactions
            WHERE user_id = ? AND type = 'expense' AND category = ?
            AND date BETWEEN ? AND ?
        """
        result = self.db._fetch_one(query, (user_id, category, start_date, end_date))
        return result[0] if result and result[0] is not None else 0.0

    def check_budget_exceeded(self, user_id, month, year):
        """
        Checks if any budget categories have been exceeded for a given month and year.
        Returns a list of (category, spent, budget, difference) for exceeded budgets.
        """
        exceeded_budgets = []
        # Get all budgets for the user for the given month/year
        budgets_query = "SELECT category, amount FROM budgets WHERE user_id = ? AND month = ? AND year = ?"
        budgets = self.db._fetch_all(budgets_query, (user_id, month, year))

        if not budgets:
            return [] # No budgets set for this month

        for category, budget_amount in budgets:
            spent_amount = self.get_expenses_for_category_in_month(user_id, category, month, year)
            if spent_amount > budget_amount:
                exceeded_budgets.append((category, spent_amount, budget_amount, spent_amount - budget_amount))
        return exceeded_budgets

# --- Financial Reports ---
class ReportManager:
    """Generates monthly and yearly financial reports."""
    def __init__(self, db_manager):
        self.db = db_manager
        self.transaction_manager = TransactionManager(db_manager)

    def generate_monthly_report(self, user_id, month, year):
        """Generates a detailed monthly financial report."""
        print(f"\n--- Monthly Report for {datetime.date(year, month, 1).strftime('%B %Y')} ---")

        start_date = f"{year}-{month:02d}-01"
        if month == 12:
            end_date = f"{year}-12-31"
        else:
            next_month_date = datetime.date(year, month + 1, 1)
            end_date = (next_month_date - datetime.timedelta(days=1)).strftime(DATE_FORMAT)

        # Get all transactions for the month
        transactions = self.transaction_manager.get_transactions(user_id, None, start_date, end_date)

        total_income = 0.0
        total_expense = 0.0
        income_by_category = {}
        expense_by_category = {}

        print("\nIncome:")
        if not any(t[1] == 'income' for t in transactions):
            print("  No income recorded for this month.")
        else:
            for tid, ttype, category, amount, date, desc in transactions:
                if ttype == 'income':
                    total_income += amount
                    income_by_category[category] = income_by_category.get(category, 0.0) + amount
                    print(f"  ID: {tid}, Date: {date}, Category: {category}, Amount: ${amount:.2f}, Desc: {desc}")

        print("\nExpenses:")
        if not any(t[1] == 'expense' for t in transactions):
            print("  No expenses recorded for this month.")
        else:
            for tid, ttype, category, amount, date, desc in transactions:
                if ttype == 'expense':
                    total_expense += amount
                    expense_by_category[category] = expense_by_category.get(category, 0.0) + amount
                    print(f"  ID: {tid}, Date: {date}, Category: {category}, Amount: ${amount:.2f}, Desc: {desc}")

        print("\n--- Summary ---")
        print(f"Total Income: ${total_income:.2f}")
        print(f"Total Expenses: ${total_expense:.2f}")
        savings = total_income - total_expense
        print(f"Net Savings/Loss: ${savings:.2f}")

        print("\nIncome by Category:")
        if income_by_category:
            for category, amount in income_by_category.items():
                print(f"  {category}: ${amount:.2f}")
        else:
            print("  N/A")

        print("\nExpenses by Category:")
        if expense_by_category:
            for category, amount in expense_by_category.items():
                print(f"  {category}: ${amount:.2f}")
        else:
            print("  N/A")

        # Check budgets for the month
        budget_manager = BudgetManager(self.db)
        exceeded_budgets = budget_manager.check_budget_exceeded(user_id, month, year)
        if exceeded_budgets:
            print("\n--- Budget Overages ---")
            for cat, spent, budget, diff in exceeded_budgets:
                print(f"  Category '{cat}': Spent ${spent:.2f} (Budget: ${budget:.2f}). Over by ${diff:.2f}!")
        else:
            print("\nNo budget limits exceeded this month.")
        print("---------------------------------------")

    def generate_yearly_report(self, user_id, year):
        """Generates a summary yearly financial report."""
        print(f"\n--- Yearly Report for {year} ---")

        start_date = f"{year}-01-01"
        end_date = f"{year}-12-31"

        transactions = self.transaction_manager.get_transactions(user_id, None, start_date, end_date)

        total_income_year = 0.0
        total_expense_year = 0.0
        income_by_month = {i: 0.0 for i in range(1, 13)}
        expense_by_month = {i: 0.0 for i in range(1, 13)}

        for tid, ttype, category, amount, date_str, desc in transactions:
            month = datetime.datetime.strptime(date_str, DATE_FORMAT).month
            if ttype == 'income':
                total_income_year += amount
                income_by_month[month] += amount
            elif ttype == 'expense':
                total_expense_year += amount
                expense_by_month[month] += amount

        print("\nMonthly Breakdown:")
        print(f"{'Month':<10} {'Income':>10} {'Expenses':>10} {'Savings':>10}")
        print("-" * 45)
        for month in range(1, 13):
            month_name = datetime.date(year, month, 1).strftime('%b')
            monthly_savings = income_by_month[month] - expense_by_month[month]
            print(f"{month_name:<10} {income_by_month[month]:>10.2f} {expense_by_month[month]:>10.2f} {monthly_savings:>10.2f}")

        print("\n--- Annual Summary ---")
        print(f"Total Annual Income: ${total_income_year:.2f}")
        print(f"Total Annual Expenses: ${total_expense_year:.2f}")
        annual_savings = total_income_year - total_expense_year
        print(f"Net Annual Savings/Loss: ${annual_savings:.2f}")
        print("---------------------------------------")

# --- Data Persistence (Backup/Restore) ---
class DataPersistence:
    """Handles backing up and restoring database files."""
    def __init__(self, db_name=DB_NAME, backup_dir=BACKUP_DIR):
        self.db_name = db_name
        self.backup_dir = backup_dir
        os.makedirs(self.backup_dir, exist_ok=True) # Ensure backup directory exists

    def backup_data(self):
        """Creates a timestamped backup of the database."""
        timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_file = os.path.join(self.backup_dir, f"{self.db_name}_backup_{timestamp}.db")
        try:
            shutil.copyfile(self.db_name, backup_file)
            print(f"Database backed up successfully to: {backup_file}")
            return True
        except FileNotFoundError:
            print(f"Error: Database file '{self.db_name}' not found.")
            return False
        except Exception as e:
            print(f"Error backing up database: {e}")
            return False

    def restore_data(self, backup_file):
        """Restores the database from a specified backup file."""
        if not os.path.exists(backup_file):
            print(f"Error: Backup file '{backup_file}' not found.")
            return False
        try:
            # Close existing connection before restoring
            if db_manager.conn:
                db_manager.close()
            shutil.copyfile(backup_file, self.db_name)
            # Re-establish connection after restore
            db_manager._connect()
            print(f"Database restored successfully from: {backup_file}")
            return True
        except Exception as e:
            print(f"Error restoring database: {e}")
            return False

    def list_backups(self):
        """Lists available backup files."""
        backups = [f for f in os.listdir(self.backup_dir) if f.startswith(self.db_name) and f.endswith('.db')]
        if not backups:
            print("No backups found.")
            return []
        print("\nAvailable Backups:")
        for i, b in enumerate(backups):
            print(f"  {i+1}. {b}")
        return backups

# --- Main Application Logic (CLI) ---
db_manager = None # Global instance for database manager
current_user_id = None
user_manager = None
transaction_manager = None
budget_manager = None
report_manager = None
data_persistence = None

def initialize_app():
    """Initializes all managers and the database connection."""
    global db_manager, user_manager, transaction_manager, budget_manager, report_manager, data_persistence
    db_manager = DBManager()
    user_manager = UserManager(db_manager)
    transaction_manager = TransactionManager(db_manager)
    budget_manager = BudgetManager(db_manager)
    report_manager = ReportManager(db_manager)
    data_persistence = DataPersistence()

def get_user_input(prompt, type_func=str):
    """Helper function to get user input with basic error handling."""
    while True:
        try:
            return type_func(input(prompt).strip())
        except ValueError:
            print("Invalid input. Please try again.")

def login_menu():
    """Handles user login and registration."""
    global current_user_id
    while current_user_id is None:
        print("\n--- Welcome to Personal Finance Manager ---")
        print("1. Login")
        print("2. Register")
        print("3. Exit")
        choice = get_user_input("Enter your choice: ", int)

        if choice == 1:
            username = get_user_input("Enter username: ")
            password = get_user_input("Enter password: ")
            current_user_id = user_manager.authenticate_user(username, password)
        elif choice == 2:
            username = get_user_input("Enter new username: ")
            password = get_user_input("Enter new password: ")
            if user_manager.register_user(username, password):
                print("Registration successful. Please login.")
            else:
                print("Registration failed.")
        elif choice == 3:
            print("Exiting application. Goodbye!")
            if db_manager:
                db_manager.close()
            exit()
        else:
            print("Invalid choice. Please try again.")

def add_transaction_menu(trans_type):
    """Menu for adding income or expense."""
    print(f"\n--- Add {trans_type.capitalize()} ---")
    print(f"Available categories for {trans_type}: {', '.join(transaction_manager.categories[trans_type])}")

    while True:
        category = get_user_input("Enter category: ").strip()
        if category in transaction_manager.categories[trans_type]:
            break
        else:
            print("Invalid category. Please choose from the list.")

    amount = get_user_input("Enter amount: ", float)
    date_str = get_user_input(f"Enter date (YYYY-MM-DD, e.g., {datetime.date.today().strftime(DATE_FORMAT)}): ")
    description = get_user_input("Enter description (optional): ")

    transaction_manager.add_transaction(current_user_id, trans_type, category, amount, date_str, description)

def view_transactions_menu():
    """Menu for viewing transactions."""
    print("\n--- View Transactions ---")
    print("1. View All")
    print("2. View Income Only")
    print("3. View Expenses Only")
    print("4. View by Date Range")
    choice = get_user_input("Enter your choice: ", int)

    trans_type = None
    start_date = None
    end_date = None

    if choice == 1:
        pass
    elif choice == 2:
        trans_type = 'income'
    elif choice == 3:
        trans_type = 'expense'
    elif choice == 4:
        start_date = get_user_input("Enter start date (YYYY-MM-DD): ")
        end_date = get_user_input("Enter end date (YYYY-MM-DD): ")
    else:
        print("Invalid choice.")
        return

    transactions = transaction_manager.get_transactions(current_user_id, trans_type, start_date, end_date)

    if not transactions:
        print("No transactions found matching your criteria.")
        return

    print("\n--- Your Transactions ---")
    print(f"{'ID':<5} {'Type':<8} {'Category':<15} {'Amount':>10} {'Date':<12} {'Description':<30}")
    print("-" * 80)
    for tid, ttype, category, amount, date_str, desc in transactions:
        print(f"{tid:<5} {ttype:<8} {category:<15} {amount:>10.2f} {date_str:<12} {desc:<30}")
    print("-" * 80)

def update_delete_transaction_menu():
    """Menu for updating or deleting transactions."""
    print("\n--- Update/Delete Transaction ---")
    view_transactions_menu() # Show transactions first

    transaction_id = get_user_input("Enter ID of transaction to update/delete: ", int)

    # Fetch the transaction to get its type and confirm ownership
    query = "SELECT type FROM transactions WHERE id = ? AND user_id = ?"
    result = db_manager._fetch_one(query, (transaction_id, current_user_id))
    if not result:
        print(f"Transaction with ID {transaction_id} not found or does not belong to you.")
        return

    original_type = result[0]

    print("\n1. Update Transaction")
    print("2. Delete Transaction")
    choice = get_user_input("Enter your choice: ", int)

    if choice == 1:
        print(f"\n--- Update Transaction ID {transaction_id} (Type: {original_type}) ---")
        print(f"Available categories for {original_type}: {', '.join(transaction_manager.categories[original_type])}")

        while True:
            category = get_user_input("Enter new category: ").strip()
            if category in transaction_manager.categories[original_type]:
                break
            else:
                print("Invalid category. Please choose from the list.")

        amount = get_user_input("Enter new amount: ", float)
        date_str = get_user_input("Enter new date (YYYY-MM-DD): ")
        description = get_user_input("Enter new description (optional): ")
        transaction_manager.update_transaction(current_user_id, transaction_id, original_type, category, amount, date_str, description)
    elif choice == 2:
        confirm = get_user_input(f"Are you sure you want to delete transaction ID {transaction_id}? (yes/no): ").lower()
        if confirm == 'yes':
            transaction_manager.delete_transaction(current_user_id, transaction_id)
        else:
            print("Deletion cancelled.")
    else:
        print("Invalid choice.")

def set_budget_menu():
    """Menu for setting a budget."""
    print("\n--- Set Monthly Budget ---")
    print(f"Available expense categories: {', '.join(transaction_manager.categories['expense'])}")

    while True:
        category = get_user_input("Enter expense category for budget: ").strip()
        if category in transaction_manager.categories['expense']:
            break
        else:
            print("Invalid category. Please choose from the list.")

    amount = get_user_input("Enter budget amount: ", float)
    month = get_user_input("Enter month (1-12): ", int)
    year = get_user_input("Enter year (e.g., 2023): ", int)

    budget_manager.set_budget(current_user_id, category, amount, month, year)

def view_budget_status_menu():
    """Menu for viewing budget status."""
    print("\n--- View Budget Status ---")
    month = get_user_input("Enter month (1-12): ", int)
    year = get_user_input("Enter year (e.g., 2023): ", int)

    print(f"\nBudget Status for {datetime.date(year, month, 1).strftime('%B %Y')}:")
    print(f"{'Category':<15} {'Budget':>10} {'Spent':>10} {'Remaining/Over':>15}")
    print("-" * 55)

    # Get all budgets for the user for the given month/year
    budgets_query = "SELECT category, amount FROM budgets WHERE user_id = ? AND month = ? AND year = ?"
    budgets = db_manager._fetch_all(budgets_query, (current_user_id, month, year))

    if not budgets:
        print("No budgets set for this month.")
        return

    for category, budget_amount in budgets:
        spent_amount = budget_manager.get_expenses_for_category_in_month(current_user_id, category, month, year)
        remaining_or_over = budget_amount - spent_amount
        status_color = ""
        if remaining_or_over < 0:
            status_color = "(OVER)" # Indicate over budget
        print(f"{category:<15} {budget_amount:>10.2f} {spent_amount:>10.2f} {remaining_or_over:>15.2f} {status_color}")
    print("-" * 55)

    exceeded_budgets = budget_manager.check_budget_exceeded(current_user_id, month, year)
    if exceeded_budgets:
        print("\n--- Budget Overages ---")
        for cat, spent, budget, diff in exceeded_budgets:
            print(f"  Category '{cat}': Spent ${spent:.2f} (Budget: ${budget:.2f}). Over by ${diff:.2f}!")

def generate_report_menu():
    """Menu for generating financial reports."""
    print("\n--- Generate Financial Report ---")
    print("1. Monthly Report")
    print("2. Yearly Report")
    choice = get_user_input("Enter your choice: ", int)

    if choice == 1:
        month = get_user_input("Enter month (1-12): ", int)
        year = get_user_input("Enter year (e.g., 2023): ", int)
        report_manager.generate_monthly_report(current_user_id, month, year)
    elif choice == 2:
        year = get_user_input("Enter year (e.g., 2023): ", int)
        report_manager.generate_yearly_report(current_user_id, year)
    else:
        print("Invalid choice.")

def data_persistence_menu():
    """Menu for data backup and restore."""
    print("\n--- Data Backup & Restore ---")
    print("1. Backup Data")
    print("2. Restore Data")
    print("3. List Backups")
    choice = get_user_input("Enter your choice: ", int)

    if choice == 1:
        data_persistence.backup_data()
    elif choice == 2:
        backups = data_persistence.list_backups()
        if backups:
            backup_choice = get_user_input("Enter the number of the backup to restore: ", int)
            if 1 <= backup_choice <= len(backups):
                selected_backup_file = os.path.join(BACKUP_DIR, backups[backup_choice - 1])
                data_persistence.restore_data(selected_backup_file)
            else:
                print("Invalid backup number.")
    elif choice == 3:
        data_persistence.list_backups()
    else:
        print("Invalid choice.")

def logged_in_menu():
    """Main menu for logged-in users."""
    global current_user_id 
    while True:
        print(f"\n--- Main Menu (User ID: {current_user_id}) ---")
        print("1. Add Income")
        print("2. Add Expense")
        print("3. View Transactions")
        print("4. Update/Delete Transaction")
        print("5. Set Budget")
        print("6. View Budget Status")
        print("7. Generate Financial Report")
        print("8. Data Backup/Restore")
        print("9. Logout")
        print("10. Exit Application")

        choice = get_user_input("Enter your choice: ", int)

        if choice == 1:
            add_transaction_menu('income')
        elif choice == 2:
            add_transaction_menu('expense')
        elif choice == 3:
            view_transactions_menu()
        elif choice == 4:
            update_delete_transaction_menu()
        elif choice == 5:
            set_budget_menu()
        elif choice == 6:
            view_budget_status_menu()
        elif choice == 7:
            generate_report_menu()
        elif choice == 8:
            data_persistence_menu()
        elif choice == 9:
            
            current_user_id = None
            print("Logged out successfully.")
            break # Go back to login menu
        elif choice == 10:
            print("Exiting application. Goodbye!")
            if db_manager:
                db_manager.close()
            exit()
        else:
            print("Invalid choice. Please try again.")

def main():
    """Main function to run the application."""
    initialize_app()
    while True:
        if current_user_id is None:
            login_menu()
        else:
            logged_in_menu()

if __name__ == "__main__":
    main()
