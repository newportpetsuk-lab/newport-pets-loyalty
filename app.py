from flask import Flask, render_template, request, session, redirect, url_for
import sqlite3
import qrcode
import os
from datetime import datetime

app = Flask(__name__)
app.secret_key = "change_this_to_something_random"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "customers.db")
QR_DIR = os.path.join(BASE_DIR, "static", "qrcodes")

os.makedirs(QR_DIR, exist_ok=True)

# -------------------------
# DATABASE
# -------------------------

def get_db():
    return sqlite3.connect(DB_PATH)

def init_db():
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS customers(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        forename TEXT,
        surname TEXT,
        phone TEXT,
        email TEXT,
        points INTEGER DEFAULT 0
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS transactions(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        customer_id INTEGER,
        points INTEGER,
        amount REAL,
        reason TEXT,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    """)

    conn.commit()
    conn.close()

init_db()

# -------------------------
# HOME
# -------------------------

@app.route("/")
def home():
    return render_template("signup.html")

# -------------------------
# SIGNUP
# -------------------------

@app.route("/signup", methods=["GET", "POST"])
def signup():

    if request.method == "POST":

        forename = request.form["forename"]
        surname = request.form["surname"]
        phone = request.form["phone"]
        email = request.form["email"]

        conn = get_db()
        cursor = conn.cursor()

        cursor.execute("""
        INSERT INTO customers(forename, surname, phone, email)
        VALUES(?, ?, ?, ?)
        """, (forename, surname, phone, email))

        customer_id = cursor.lastrowid

        conn.commit()
        conn.close()

        formatted_id = "NP" + str(customer_id).zfill(5)

        qr = qrcode.make(formatted_id)
        qr.save(os.path.join(QR_DIR, f"qr_{formatted_id}.png"))

        return render_template(
            "welcome.html",
            forename=forename,
            customer_id=formatted_id
        )

    return render_template("signup.html")

# -------------------------
# SCAN
# -------------------------

@app.route("/scan", methods=["GET", "POST"])
def scan():

    customer = None
    error = None

    if request.method == "POST":

        customer_id = request.form["customer_id"].replace("NP", "")

        conn = get_db()
        cursor = conn.cursor()

        cursor.execute("SELECT id, forename, surname, points FROM customers WHERE id=?", (customer_id,))
        customer = cursor.fetchone()

        conn.close()

        if not customer:
            error = "Customer not found"

    return render_template("scan.html", customer=customer, error=error)

# -------------------------
# ADD POINTS
# -------------------------

@app.route("/addpoints", methods=["POST"])
def addpoints():

    customer_id = request.form["customer_id"].replace("NP", "")
    amount = float(request.form["amount"])

    points = int(amount)

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("UPDATE customers SET points = points + ? WHERE id=?", (points, customer_id))

    cursor.execute("""
    INSERT INTO transactions (customer_id, points, amount, reason)
    VALUES (?, ?, ?, ?)
    """, (customer_id, points, amount, "Purchase"))

    conn.commit()
    conn.close()

    return redirect("/scan")

# -------------------------
# REDEEM
# -------------------------

@app.route("/redeem", methods=["POST"])
def redeem():

    customer_id = request.form["customer_id"].replace("NP", "")
    redeem_amount = int(request.form.get("redeem_amount", 2))

    points_needed = (redeem_amount // 2) * 150

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT points FROM customers WHERE id=?", (customer_id,))
    current_points = cursor.fetchone()[0]

    if current_points >= points_needed:

        cursor.execute("UPDATE customers SET points = points - ? WHERE id=?", (points_needed, customer_id))

        cursor.execute("""
        INSERT INTO transactions (customer_id, points, amount, reason)
        VALUES (?, ?, ?, ?)
        """, (customer_id, -points_needed, -redeem_amount, "Reward redeemed"))

        conn.commit()
        message = f"Apply £{redeem_amount} discount"

    else:
        message = "Not enough points"

    conn.close()

    return render_template("redeem.html", message=message)

# -------------------------
# HISTORY
# -------------------------

@app.route("/history/<customer_id>")
def history(customer_id):

    customer_id = customer_id.replace("NP", "")

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
    SELECT points, amount, reason, timestamp
    FROM transactions
    WHERE customer_id=?
    ORDER BY timestamp DESC
    """, (customer_id,))

    transactions = cursor.fetchall()
    conn.close()

    return render_template("history.html", transactions=transactions, customer_id=customer_id)
