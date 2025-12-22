from flask import Flask, render_template, request, redirect, url_for, session, flash, Response
from flask_session import Session
import sqlite3
import datetime
import csv
import io

app = Flask(__name__)
app.secret_key = "your-secret-key"
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

DATABASE = 'pebi.db'  # SQLite database file

def get_db_connection():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row  # To access columns by name
    return conn

# Create tables if they do not exist
def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            email TEXT NOT NULL
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS bills (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            bill_type TEXT NOT NULL,
            bill_date DATE NOT NULL,
            due_date DATE NOT NULL,
            payment_status TEXT NOT NULL,
            payment_method TEXT NOT NULL,
            amount REAL NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    ''')
    conn.commit()
    cursor.close()
    conn.close()

# Initialize the database
init_db()

# First page: Ask if new or existing user
@app.route('/', methods=['GET', 'POST'])
def welcome():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    if request.method == 'POST':
        user_type = request.form.get('user_type')
        if user_type == 'new':
            return redirect(url_for('signup'))
        elif user_type == 'existing':
            return redirect(url_for('login'))
        else:
            flash("Please select a valid option.")
    return render_template('welcome.html')

# Signup page
@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        username = request.form.get('username').strip()
        email = request.form.get('email').strip()
        if not username or not email:
            flash('Please provide both username and email.')
            return render_template('signup.html')
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM users WHERE username = ?", (username,))
        if cursor.fetchone():
            flash('Username already exists.')
            cursor.close()
            conn.close()
            return render_template('signup.html')
        cursor.execute("INSERT INTO users (username, email) VALUES (?, ?)", (username, email))
        conn.commit()
        cursor.close()
        conn.close()
        flash('User created! Please log in.')
        return redirect(url_for('login'))
    return render_template('signup.html')

# Login page
@app.route('/login', methods=['GET', 'POST'])
def login():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        username = request.form.get('username').strip()
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE username = ?", (username,))
        user = cursor.fetchone()
        cursor.close()
        conn.close()
        if user:
            session['user_id'] = user['id']
            session['username'] = user['username']
            return redirect(url_for('dashboard'))
        else:
            flash('User not found. Please sign up first.')
    return render_template('login.html')

# Dashboard / Main tab with bills display, filter and CRUD links
@app.route('/dashboard', methods=['GET', 'POST'])
def dashboard():
    if 'user_id' not in session:
        flash('Please log in first.')
        return redirect(url_for('login'))

    user_id = session['user_id']
    conn = get_db_connection()
    cursor = conn.cursor()

    # Handle filter/search
    search_term = request.args.get('search', '').strip().lower()
    filter_status = request.args.get('status', '').strip().lower()
    filter_payment = request.args.get('payment_method', '').strip().lower()

    query = "SELECT * FROM bills WHERE user_id = ?"
    params = [user_id]

    conditions = []
    if search_term:
        conditions.append("(LOWER(name) LIKE ? OR LOWER(bill_type) LIKE ?)")
        params.extend([f"%{search_term}%", f"%{search_term}%"])

    if filter_status in ['pending', 'paid']:
        conditions.append("LOWER(payment_status) = ?")
        params.append(filter_status)

    if filter_payment in ['cash', 'bank', 'online', 'other']:
        conditions.append("LOWER(payment_method) = ?")
        params.append(filter_payment)

    if conditions:
        query += " AND " + " AND ".join(conditions)

    query += " ORDER BY due_date ASC"
    cursor.execute(query, params)
    bills = cursor.fetchall()

    # Prepare bills for due date highlight and payment status tag
    today = datetime.date.today()
    bills_list = []
    for bill in bills:
        bill_dict = dict(bill)
        # Convert string dates to datetime objects if they are strings
        if isinstance(bill_dict['bill_date'], str):
            bill_dict['bill_date'] = datetime.datetime.strptime(bill_dict['bill_date'], '%Y-%m-%d').date()
        if isinstance(bill_dict['due_date'], str):
            bill_dict['due_date'] = datetime.datetime.strptime(bill_dict['due_date'], '%Y-%m-%d').date()

        due_date = bill_dict['due_date']
        days_to_due = (due_date - today).days
        if days_to_due < 0:
            bill_dict['due_status'] = 'overdue'
        elif days_to_due <= 3:
            bill_dict['due_status'] = 'near_due'
        else:
            bill_dict['due_status'] = 'normal'
        bill_dict['is_pending'] = (bill_dict['payment_status'].lower() == 'pending')
        bills_list.append(bill_dict)

    cursor.close()
    conn.close()

    return render_template('dashboard.html', username=session.get('username'), bills=bills_list, search_term=search_term, filter_status=filter_status, filter_payment=filter_payment)

# Add bill (form)
@app.route('/add_bill', methods=['GET', 'POST'])
def add_bill():
    if 'user_id' not in session:
        flash('Please log in first.')
        return redirect(url_for('login'))

    bill_types = ['Electricity', 'Water', 'Internet', 'Rent', 'Other']
    payment_methods = ['Cash', 'Bank', 'Online', 'Other']

    if request.method == 'POST':
        name = request.form.get('name').strip()
        bill_type = request.form.get('bill_type').strip()
        bill_date = request.form.get('bill_date').strip()
        due_date = request.form.get('due_date').strip()
        payment_status = request.form.get('payment_status', 'Pending').strip()
        payment_method = request.form.get('payment_method').strip()
        amount = request.form.get('amount').strip()

        if not all([name, bill_type, bill_date, due_date, payment_method, amount]):
            flash('All fields except payment status are required.')
            return render_template('add_bill.html', bill_types=bill_types, payment_methods=payment_methods)

        try:
            datetime.datetime.strptime(bill_date, '%Y-%m-%d')
            datetime.datetime.strptime(due_date, '%Y-%m-%d')
            amount = float(amount)
        except ValueError:
            flash('Date format must be YYYY-MM-DD and amount must be a number.')
            return render_template('add_bill.html', bill_types=bill_types, payment_methods=payment_methods)

        user_id = session['user_id']
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM bills WHERE user_id = ? AND LOWER(name) = LOWER(?)", (user_id, name))
        if cursor.fetchone():
            flash('A bill with this name already exists.')
            cursor.close()
            conn.close()
            return render_template('add_bill.html', bill_types=bill_types, payment_methods=payment_methods)

        cursor.execute(
            "INSERT INTO bills (user_id, name, bill_type, bill_date, due_date, payment_status, payment_method, amount) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (user_id, name, bill_type, bill_date, due_date, payment_status, payment_method, amount)
        )
        conn.commit()
        cursor.close()
        conn.close()
        flash('Bill added successfully.')
        return redirect(url_for('dashboard'))

    return render_template('add_bill.html', bill_types=bill_types, payment_methods=payment_methods)

# Edit bill
@app.route('/edit_bill/<int:bill_id>', methods=['GET', 'POST'])
def edit_bill(bill_id):
    if 'user_id' not in session:
        flash('Please log in first.')
        return redirect(url_for('login'))

    bill_types = ['Electricity', 'Water', 'Internet', 'Rent', 'Other']
    payment_methods = ['Cash', 'Bank', 'Online', 'Other']

    user_id = session['user_id']
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM bills WHERE id = ? AND user_id = ?", (bill_id, user_id))
    bill = cursor.fetchone()

    if not bill:
        cursor.close()
        conn.close()
        flash('Bill not found or access denied.')
        return redirect(url_for('dashboard'))

    bill_dict = dict(bill)
    # Convert dates to date objects for template usage
    if isinstance(bill_dict['bill_date'], str):
        bill_dict['bill_date'] = datetime.datetime.strptime(bill_dict['bill_date'], '%Y-%m-%d').date()
    if isinstance(bill_dict['due_date'], str):
        bill_dict['due_date'] = datetime.datetime.strptime(bill_dict['due_date'], '%Y-%m-%d').date()

    if request.method == 'POST':
        name = request.form.get('name').strip()
        bill_type = request.form.get('bill_type').strip()
        bill_date = request.form.get('bill_date').strip()
        due_date = request.form.get('due_date').strip()
        payment_status = request.form.get('payment_status').strip()
        payment_method = request.form.get('payment_method').strip()
        amount = request.form.get('amount').strip()

        if not all([name, bill_type, bill_date, due_date, payment_status, payment_method, amount]):
            flash('All fields are required.')
            return render_template('edit_bill.html', bill=bill_dict, bill_types=bill_types, payment_methods=payment_methods)

        try:
            datetime.datetime.strptime(bill_date, '%Y-%m-%d')
            datetime.datetime.strptime(due_date, '%Y-%m-%d')
            amount = float(amount)
        except ValueError:
            flash('Date format must be YYYY-MM-DD and amount must be a number.')
            return render_template('edit_bill.html', bill=bill_dict, bill_types=bill_types, payment_methods=payment_methods)

        cursor.execute("SELECT id FROM bills WHERE user_id = ? AND LOWER(name) = LOWER(?) AND id != ?", 
                       (user_id, name, bill_id))
        if cursor.fetchone():
            flash('Another bill with this name already exists.')
            return render_template('edit_bill.html', bill=bill_dict, bill_types=bill_types, payment_methods=payment_methods)

        cursor.execute(
            "UPDATE bills SET name=?, bill_type=?, bill_date=?, due_date=?, payment_status=?, payment_method=?, amount=? WHERE id=? AND user_id=?",
            (name, bill_type, bill_date, due_date, payment_status, payment_method, amount, bill_id, user_id)
        )
        conn.commit()
        cursor.close()
        conn.close()
        flash('Bill updated successfully.')
        return redirect(url_for('dashboard'))

    cursor.close()
    conn.close()
    return render_template('edit_bill.html', bill=bill_dict, bill_types=bill_types, payment_methods=payment_methods)

# Delete bill
@app.route('/delete_bill/<int:bill_id>', methods=['POST'])
def delete_bill(bill_id):
    if 'user_id' not in session:
        flash('Please log in first.')
        return redirect(url_for('login'))

    user_id = session['user_id']
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM bills WHERE id = ? AND user_id = ?", (bill_id, user_id))
    conn.commit()
    cursor.close()
    conn.close()

    flash('Bill deleted successfully.')
    return redirect(url_for('dashboard'))

# Download bills backup as CSV
@app.route('/download_backup')
def download_backup():
    if 'user_id' not in session:
        flash('Please log in first.')
        return redirect(url_for('login'))

    user_id = session['user_id']
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM bills WHERE user_id = ? ORDER BY due_date ASC", (user_id,))
    bills = cursor.fetchall()
    cursor.close()
    conn.close()

    # Create CSV content
    si = io.StringIO()
    cw = csv.writer(si)
    header = ['name', 'bill_type', 'bill_date', 'due_date', 'payment_status', 'payment_method', 'amount']
    cw.writerow(header)
    for bill in bills:
        # Convert dates to string for CSV output if necessary
        bill_date = bill['bill_date']
        due_date = bill['due_date']

        # In case they are datetime objects stored in DB (unlikely)
        if not isinstance(bill_date, str):
            bill_date = bill_date.strftime('%Y-%m-%d')
        if not isinstance(due_date, str):
            due_date = due_date.strftime('%Y-%m-%d')

        cw.writerow([
            bill['name'],
            bill['bill_type'],
            bill_date,
            due_date,
            bill['payment_status'],
            bill['payment_method'],
            bill['amount']
        ])

    output = si.getvalue()
    return Response(output, mimetype="text/csv", headers={"Content-disposition": "attachment; filename=bills_backup.csv"})

@app.route('/visualization')
def visualization():
    if 'user_id' not in session:
        flash('Please log in first.')
        return redirect(url_for('login'))

    user_id = session['user_id']
    conn = get_db_connection()
    cursor = conn.cursor()

    # Get total users
    cursor.execute("SELECT COUNT(*) FROM users")
    total_users = cursor.fetchone()[0]

    # Get total bills for the logged-in user
    cursor.execute("SELECT COUNT(*) FROM bills WHERE user_id = ?", (user_id,))
    total_bills = cursor.fetchone()[0]

    # Get total amount due (sum of amounts where payment status is not 'Paid')
    cursor.execute("SELECT SUM(amount) FROM bills WHERE user_id = ? AND payment_status != 'Paid'", (user_id,))
    total_due = cursor.fetchone()[0] or 0

    # Get total amount paid
    cursor.execute("SELECT SUM(amount) FROM bills WHERE user_id = ? AND payment_status = 'Paid'", (user_id,))
    total_paid = cursor.fetchone()[0] or 0

    # Calculate percentage of paid bills
    total_amount = total_due + total_paid
    amount_due_percentage = (total_paid / total_amount * 100) if total_amount > 0 else 0

    # Get monthly bill amounts
    cursor.execute("""
        SELECT strftime('%Y-%m', bill_date) AS month, SUM(amount) AS total_amount
        FROM bills
        WHERE user_id = ?
        GROUP BY month
        ORDER BY month
    """, (user_id,))
    monthly_bills = cursor.fetchall()

    # Get payment status counts
    cursor.execute("""
        SELECT payment_status, COUNT(*) AS count
        FROM bills
        WHERE user_id = ?
        GROUP BY payment_status
    """, (user_id,))
    payment_status_counts = cursor.fetchall()

    # Get payment method counts
    cursor.execute("""
        SELECT payment_method, COUNT(*) AS count
        FROM bills
        WHERE user_id = ?
        GROUP BY payment_method
    """, (user_id,))
    payment_method_counts = cursor.fetchall()

    # Get the first five highest bills
    cursor.execute("""
        SELECT name, amount
        FROM bills
        WHERE user_id = ?
        ORDER BY amount DESC
        LIMIT 5
    """, (user_id,))
    highest_bills = cursor.fetchall()

    cursor.close()
    conn.close()

    return render_template('visualization.html', 
                           total_users=total_users, 
                           total_bills=total_bills,
                           amount_due=total_due,  # Pass the total due amount
                           amount_due_percentage=amount_due_percentage, 
                           monthly_bills=monthly_bills,
                           payment_status_counts=payment_status_counts, 
                           payment_method_counts=payment_method_counts,
                           highest_bills=highest_bills)

# Logout
@app.route('/logout')
def logout():
    session.clear()
    flash('Logged out successfully.')
    return redirect(url_for('login'))

if __name__ == "__main__":
    app.run(debug=True)

