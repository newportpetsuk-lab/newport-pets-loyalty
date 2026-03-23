# version 1.0.1

from flask import Flask, render_template, request, session, redirect, url_for, send_file
import sqlite3
import qrcode
import os
import io
from datetime import datetime
import smtplib
from email.mime.text import MIMEText

app = Flask(__name__)
app.secret_key = "change_this_to_a_random_secret_key"

# -------------------------
# EMAIL FUNCTION
# -------------------------

def send_email(to_email, forename, customer_id):

    body = f"""
Hi {forename},

Welcome to Newport Pets Rewards!

Your customer ID: {customer_id}

Show your QR code in-store to collect points.

Visit:
https://newport-loyalty-final.onrender.com/

Thank you for supporting Newport Pets!
"""

    msg = MIMEText(body)
    msg["Subject"] = "Welcome to Newport Pets Rewards"
    msg["From"] = "your_email@gmail.com"
    msg["To"] = to_email

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login("newportpetsuk@gmail.com", "Jonsteinn@93@")
            server.send_message(msg)
    except Exception as e:
        print("EMAIL ERROR:", e)

# -------------------------
# CONFIG
# -------------------------

DATABASE_URL = os.getenv("DATABASE_URL")

# Fix Render Postgres URL
if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SQLITE_PATH = os.path.join(BASE_DIR, "customers.db")

STAFF_USERNAME = os.getenv("STAFF_USERNAME", "admin")
STAFF_PASSWORD = os.getenv("STAFF_PASSWORD", "newport1003!")

# -------------------------
# DATABASE HELPERS
# -------------------------

def is_postgres():
    return DATABASE_URL is not None and DATABASE_URL.strip() != ""


def get_connection():
    if is_postgres():
        import psycopg2
        return psycopg2.connect(DATABASE_URL, connect_timeout=5)
    else:
        return sqlite3.connect(SQLITE_PATH)


def p():
    return "%s" if is_postgres() else "?"


def get_insert_id(cursor):
    if is_postgres():
        return cursor.fetchone()[0]
    else:
        return cursor.lastrowid


def parse_customer_id(customer_id):
    customer_id = customer_id.strip().upper()
    if customer_id.startswith("NP"):
        return int(customer_id[2:])
    return int(customer_id)


# -------------------------
# DATABASE INITIALISATION
# -------------------------

def init_db():
    conn = get_connection()
    cursor = conn.cursor()

    if is_postgres():
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS customers(
            id SERIAL PRIMARY KEY,
            forename TEXT,
            surname TEXT,
            phone TEXT,
            email TEXT,
            points INTEGER DEFAULT 0
        )
        """)

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS transactions(
            id SERIAL PRIMARY KEY,
            customer_id INTEGER,
            points INTEGER,
            amount REAL,
            reason TEXT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)
    else:
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


try:
    init_db()
except Exception as e:
    print("DB INIT ERROR:", e)


# -------------------------
# QR GENERATION (FIXED)
# -------------------------

@app.route("/qr/<customer_id>")
def generate_qr(customer_id):
    img = qrcode.make(customer_id)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return send_file(buf, mimetype="image/png")


# -------------------------
# LOGIN
# -------------------------

@app.route("/login", methods=["GET", "POST"])
def login():
    error = None

    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]

        if username == STAFF_USERNAME and password == STAFF_PASSWORD:
            session["logged_in"] = True
            return redirect("/scan")
        else:
            error = "Invalid login"

    return render_template("login.html", error=error)


@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")


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

        conn = get_connection()
        cursor = conn.cursor()

        if is_postgres():
            cursor.execute(f"""
            INSERT INTO customers(forename, surname, phone, email)
            VALUES({p()}, {p()}, {p()}, {p()})
            RETURNING id
            """, (forename, surname, phone, email))
        else:
            cursor.execute("""
            INSERT INTO customers(forename, surname, phone, email)
            VALUES(?, ?, ?, ?)
            """, (forename, surname, phone, email))

        customer_id = get_insert_id(cursor)

        conn.commit()
        conn.close()

        formatted_id = "NP" + str(customer_id).zfill(5)

        send_email(email, forename, formatted_id)

        return render_template(
            "welcome.html",
            forename=forename,
            customer_id=formatted_id
        )

    return render_template("signup.html")


# -------------------------
# SCAN CUSTOMER
# -------------------------

@app.route("/scan", methods=["GET", "POST"])
def scan():

    if not session.get("logged_in"):
        return redirect("/login")

    customer = None
    customer_id = None
    error = None
    redeem_options = []   # ✅ ALWAYS defined

    if request.method == "POST":

        customer_id = request.form.get("customer_id", "").strip().upper()

        if customer_id == "":
            error = "Please scan or enter a customer ID"
            return render_template("scan.html", error=error)

        try:
            id_number = parse_customer_id(customer_id)

            conn = get_connection()
            cursor = conn.cursor()

            cursor.execute(
                f"SELECT id, forename, surname, points FROM customers WHERE id={p()}",
                (id_number,)
            )

            customer = cursor.fetchone()
            conn.close()

            if customer:
                points = customer[3]

                # ✅ Calculate available rewards
                max_rewards = points // 150

                for i in range(1, max_rewards + 1):
                    redeem_options.append(i * 2)

            else:
                error = "Customer not found"

        except:
            error = "Invalid customer ID"

    return render_template(
        "scan.html",
        customer=customer,
        customer_id=customer_id,
        error=error,
        redeem_options=redeem_options
    )


# -------------------------
# ADD POINTS
# -------------------------

@app.route("/addpoints", methods=["POST"])
def addpoints():

    if not session.get("logged_in"):
        return redirect("/login")

    customer_id = request.form["customer_id"].strip().upper()

    fish_amount = float(request.form.get("fish_amount", "0") or 0)
    other_amount = float(request.form.get("other_amount", "0") or 0)
    excluded_amount = float(request.form.get("excluded_amount", "0") or 0)

    points = int(fish_amount * 2 + other_amount)
    total_amount = fish_amount + other_amount + excluded_amount

    id_number = parse_customer_id(customer_id)

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        f"UPDATE customers SET points = points + {p()} WHERE id={p()}",
        (points, id_number)
    )

    cursor.execute(
        f"INSERT INTO transactions (customer_id, points, amount, reason) VALUES ({p()}, {p()}, {p()}, {p()})",
        (id_number, points, total_amount, "Purchase")
    )

    cursor.execute(
        f"SELECT forename, surname, points FROM customers WHERE id={p()}",
        (id_number,)
    )

    customer = cursor.fetchone()

    conn.commit()
    conn.close()

    new_points = customer[2]
    earned_today = points // 150 * 2
    total_rewards = new_points // 150 * 2

    formatted_id = "NP" + str(id_number).zfill(5)

    return render_template(
        "points_added.html",
        forename=customer[0],
        surname=customer[1],
        customer_id=formatted_id,   # 👈 FIX HERE
        points_added=points,
        new_points=new_points,
        earned_today=earned_today,
        total_rewards=total_rewards
    )


# -------------------------
# REDEEM
# -------------------------

@app.route("/redeem", methods=["POST"])
def redeem():

    if not session.get("logged_in"):
        return redirect("/login")

    customer_id = request.form["customer_id"]
    id_number = int(customer_id[2:])

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        f"SELECT points FROM customers WHERE id={p()}",
        (id_number,)
    )
    current_points = cursor.fetchone()[0]

    redeem_amount = int(request.form.get("redeem_amount", 2))
    points_needed = (redeem_amount // 2) * 150

    if current_points >= points_needed:

        cursor.execute(
            f"UPDATE customers SET points = points - {p()} WHERE id={p()}",
            (points_needed, id_number)
        )

        cursor.execute(
            f"INSERT INTO transactions (customer_id, points, amount, reason) VALUES ({p()}, {p()}, {p()}, {p()})",
            (id_number, -points_needed, -redeem_amount, "Reward redeemed")
        )

        conn.commit()
        message = f"Apply £{redeem_amount} discount on till"

    else:
        message = "Not enough points"

    conn.close()

    return render_template("redeem.html", message=message)

# -------------------------
# DASHBOARD
# -------------------------

@app.route("/dashboard")
def dashboard():

    if not session.get("logged_in"):
        return redirect(url_for("login"))

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) FROM customers")
    total_customers = cursor.fetchone()[0]

    cursor.execute("SELECT SUM(points) FROM transactions WHERE points > 0")
    total_points = cursor.fetchone()[0] or 0

    cursor.execute("SELECT SUM(amount) FROM transactions WHERE amount < 0")
    total_rewards = abs(cursor.fetchone()[0] or 0)

    conn.close()

    return render_template(
        "dashboard.html",
        total_customers=total_customers,
        total_points=total_points,
        total_rewards=total_rewards
    )
