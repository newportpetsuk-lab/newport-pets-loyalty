# version 1.1 (QR + Customer Page Upgrade SAFE)

from flask import Flask, render_template, request, session, redirect, url_for, send_file
import sqlite3
import qrcode
import os
import io
from datetime import datetime
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.image import MIMEImage

# -------------------------
# PATH SETUP
# -------------------------

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
QR_DIR = os.path.join(BASE_DIR, "static", "qrcodes")
os.makedirs(QR_DIR, exist_ok=True)

# -------------------------
# APP INIT
# -------------------------

app = Flask(__name__)
app.secret_key = "change_this_to_a_random_secret_key"

# -------------------------
# CONFIG
# -------------------------

DATABASE_URL = os.getenv("DATABASE_URL")

if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

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
# EMAIL FUNCTION
# -------------------------

def send_email(to_email, forename, customer_id):

    msg = MIMEMultipart()
    msg["Subject"] = "Welcome to Newport Pets Rewards"
    msg["From"] = "newportpetsuk@gmail.com"
    msg["To"] = to_email

    body = f"""
Hi {forename},

Welcome to Newport Pets Rewards!

Your customer ID: {customer_id}

Your QR code is attached — save it and show it in-store.

Thank you for supporting Newport Pets!
"""

    msg.attach(MIMEText(body, "plain"))

    try:
        qr_path = os.path.join(QR_DIR, f"qr_url_{customer_id}.png")

        with open(qr_path, "rb") as f:
            img = MIMEImage(f.read())
            img.add_header("Content-Disposition", "attachment", filename=f"{customer_id}.png")
            msg.attach(img)

        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login("newportpetsuk@gmail.com", "fokk fgay ccwo enif")
            server.send_message(msg)

        print("EMAIL SENT WITH QR")

    except Exception as e:
        print("EMAIL ERROR:", e)

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

    # ✅ SAFE ADD COLUMN
    try:
        cursor.execute("ALTER TABLE customers ADD COLUMN customer_code TEXT")
    except:
        pass

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

        # SAVE CUSTOMER CODE
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute(f"""
        UPDATE customers SET customer_code = {p()} WHERE id = {p()}
        """, (formatted_id, customer_id))

        conn.commit()
        conn.close()

        # QR 1 (SCANNER)
        qr_basic = qrcode.make(formatted_id)
        qr_basic.save(os.path.join(QR_DIR, f"qr_{formatted_id}.png"))

        # QR 2 (CUSTOMER PAGE)
        url = f"https://newport-loyalty-final.onrender.com/customer/{formatted_id}"
        qr_url = qrcode.make(url)
        qr_url.save(os.path.join(QR_DIR, f"qr_url_{formatted_id}.png"))

        # SEND EMAIL
        send_email(email, forename, formatted_id)

        return render_template(
            "welcome.html",
            forename=forename,
            customer_id=formatted_id
        )

    return render_template("signup.html")

# -------------------------
# CUSTOMER PAGE
# -------------------------

@app.route("/customer/<code>")
def customer_page(code):

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        f"SELECT forename, surname, points FROM customers WHERE customer_code = {p()}",
        (code,)
    )

    customer = cursor.fetchone()
    conn.close()

    if not customer:
        return "Customer not found"

    return render_template(
        "customer.html",
        forename=customer[0],
        surname=customer[1],
        points=customer[2],
        code=code
    )

# -------------------------
# LOGIN
# -------------------------

@app.route("/login", methods=["GET", "POST"])
def login():
    error = None

    if request.method == "POST":
        if request.form["username"] == STAFF_USERNAME and request.form["password"] == STAFF_PASSWORD:
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
# SCAN (UNCHANGED)
# -------------------------

@app.route("/scan", methods=["GET", "POST"])
def scan():

    if not session.get("logged_in"):
        return redirect("/login")

    customer = None
    customer_id = None
    error = None
    redeem_options = []

    if request.method == "POST":

        customer_id = request.form.get("customer_id", "").strip().upper()

        if customer_id == "":
            return render_template("scan.html", error="Please scan or enter a customer ID")

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
