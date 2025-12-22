import sqlite3
import random
from faker import Faker
from flask import Flask, render_template_string

app = Flask(__name__)
fake = Faker()

# Connect to SQLite database
conn = sqlite3.connect("pebi.db")
cursor = conn.cursor()

# Create tables
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

# Insert sample users
users = ["emjay", "alec", "xtian", "pebi", "heben", "abby", "juny"]
for user in users:
    cursor.execute("INSERT OR IGNORE INTO users (username, email) VALUES (?, ?)", (user, f"{user}@example.com"))

# Fetch user IDs
cursor.execute("SELECT id, username FROM users")
user_data = cursor.fetchall()

# Generate 500 random bills
bill_types = ["Electricity", "Water", "Internet", "Gas", "Rent", "Insurance"]
payment_statuses = ["Pending", "Paid", "Overdue"]
payment_methods = ["Credit Card", "Bank Transfer", "Cash", "PayPal"]

bills = [
    (
        random.choice(user_data)[0],  # Random user_id
        fake.bs().title(),  # Random bill name
        random.choice(bill_types),
        fake.date_between(start_date="-1y", end_date="today").strftime("%Y-%m-%d"),
        fake.date_between(start_date="today", end_date="+1y").strftime("%Y-%m-%d"),
        random.choice(payment_statuses),
        random.choice(payment_methods),
        round(random.uniform(50, 500), 2)  # Random amount
    )
    for _ in range(500)
]

# Insert bills
cursor.executemany("INSERT INTO bills (user_id, name, bill_type, bill_date, due_date, payment_status, payment_method, amount) VALUES (?, ?, ?, ?, ?, ?, ?, ?)", bills)
conn.commit()
conn.close()

# Flask Route to Display Bills in HTML
@app.route("/")
def show_bills():
    conn = sqlite3.connect("pebi.db")
    cursor = conn.cursor()
    cursor.execute('''
        SELECT users.username, bills.name, bills.bill_type, bills.bill_date, bills.due_date, 
               bills.payment_status, bills.payment_method, bills.amount 
        FROM bills 
        INNER JOIN users ON bills.user_id = users.id
    ''')
    data = cursor.fetchall()
    conn.close()
    
    html_template = '''
    <html>
    <head>
        <title>Bills Summary</title>
        <style>
            table {width: 80%; margin: 20px auto; border-collapse: collapse;}
            th, td {border: 1px solid black; padding: 10px; text-align: left;}
            th {background-color: #f2f2f2;}
        </style>
    </head>
    <body>
        <h2 style="text-align: center;">Bills Summary</h2>
        <table>
            <tr>
                <th>Username</th>
                <th>Bill Name</th>
                <th>Bill Type</th>
                <th>Bill Date</th>
                <th>Due Date</th>
                <th>Payment Status</th>
                <th>Payment Method</th>
                <th>Amount ($)</th>
            </tr>
            {% for row in data %}
            <tr>
                {% for item in row %}
                <td>{{ item }}</td>
                {% endfor %}
            </tr>
            {% endfor %}
        </table>
    </body>
    </html>
    '''
    return render_template_string(html_template, data=data)

if __name__ == "__main__":
    app.run(debug=True)