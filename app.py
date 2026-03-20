from flask import Flask, render_template, request
import sqlite3
import qrcode
import os

app = Flask(__name__)

DATABASE_URL = os.getenv("DATABASE_URL")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SQLITE_PATH = os.path.join(BASE_DIR, "customers.db")
QR_DIR = os.path.join(BASE_DIR, "static", "qrcodes")


# -------------------------
# DATABASE HELPERS
# -------------------------

def is_postgres():
    return DATABASE_URL is not None and DATABASE_URL.strip() != ""


def get_connection():
    if is_postgres():
        import psycopg2
        return psycopg2.connect(DATABASE_URL)
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

    os.makedirs(QR_DIR, exist_ok=True)


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

        qr = qrcode.make(formatted_id)
        qr.save(os.path.join(QR_DIR, f"qr_{formatted_id}.png"))

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

    customer = None
    customer_id = None
    error = None

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

            if not customer:
                error = "Customer not found"

        except:
            error = "Invalid customer ID"

    return render_template(
        "scan.html",
        customer=customer,
        customer_id=customer_id,
        error=error
    )


# -------------------------
# ADD POINTS
# -------------------------

@app.route("/addpoints", methods=["POST"])
def addpoints():

    customer_id = request.form["customer_id"].strip().upper()

    fish_amount = request.form.get("fish_amount", "0").replace(",", ".")
    other_amount = request.form.get("other_amount", "0").replace(",", ".")
    excluded_amount = request.form.get("excluded_amount", "0").replace(",", ".")

    fish_amount = float(fish_amount) if fish_amount else 0
    other_amount = float(other_amount) if other_amount else 0
    excluded_amount = float(excluded_amount) if excluded_amount else 0

    fish_points = int(fish_amount * 2)
    other_points = int(other_amount)

    points = fish_points + other_points
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
    reward_count = new_points // 150
    reward_value = reward_count * 2

    return render_template(
        "points_added.html",
        forename=customer[0],
        surname=customer[1],
        customer_id=customer_id,
        points_added=points,
        new_points=new_points,
        reward_count=reward_count,
        reward_value=reward_value
    )


# -------------------------
# REDEEM REWARD
# -------------------------

@app.route("/redeem", methods=["POST"])
def redeem():

    customer_id = request.form["customer_id"]
    id_number = parse_customer_id(customer_id)

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        f"SELECT points FROM customers WHERE id={p()}",
        (id_number,)
    )

    result = cursor.fetchone()
    current_points = result[0] if result else 0

    if current_points >= 150:

        cursor.execute(
            f"UPDATE customers SET points = points - 150 WHERE id={p()}",
            (id_number,)
        )

        cursor.execute(
            f"INSERT INTO transactions (customer_id, points, amount, reason) VALUES ({p()}, {p()}, {p()}, {p()})",
            (id_number, -150, -2, "Reward redeemed")
        )

        conn.commit()
        message = "£2 reward redeemed successfully"

    else:
        message = "Not enough points"

    conn.close()

    return render_template("redeem.html", message=message)


# -------------------------
# TRANSACTION HISTORY
# -------------------------

@app.route("/history/<customer_id>")
def history(customer_id):

    numeric_id = parse_customer_id(customer_id)

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(f"""
        SELECT points, amount, reason, timestamp
        FROM transactions
        WHERE customer_id = {p()}
        ORDER BY timestamp DESC
    """, (numeric_id,))

    transactions = cursor.fetchall()

    conn.close()

    return render_template(
        "history.html",
        transactions=transactions,
        customer_id=customer_id
    )


# -------------------------
# REDEEM CUSTOM
# -------------------------

@app.route("/redeem_custom", methods=["POST"])
def redeem_custom():

    customer_id = request.form["customer_id"]
    redeem_value = int(request.form["redeem_value"])

    id_number = parse_customer_id(customer_id)

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        f"SELECT forename, surname, points FROM customers WHERE id={p()}",
        (id_number,)
    )

    customer = cursor.fetchone()
    current_points = customer[2]

    points_to_deduct = (redeem_value // 2) * 150

    if current_points >= points_to_deduct:

        cursor.execute(
            f"UPDATE customers SET points = points - {p()} WHERE id={p()}",
            (points_to_deduct, id_number)
        )

        cursor.execute(
            f"INSERT INTO transactions (customer_id, points, amount, reason) VALUES ({p()}, {p()}, {p()}, {p()})",
            (id_number, -points_to_deduct, -redeem_value, "Reward redeemed")
        )

        conn.commit()

        new_points = current_points - points_to_deduct
        message = f"£{redeem_value} reward applied"

    else:
        new_points = current_points
        message = "Not enough points"

    conn.close()

    reward_count = new_points // 150
    reward_value = reward_count * 2

    return render_template(
        "points_added.html",
        forename=customer[0],
        surname=customer[1],
        customer_id=customer_id,
        points_added=0,
        new_points=new_points,
        reward_count=reward_count,
        reward_value=reward_value,
        message=message
    )


# -------------------------
# LOYALTY LOOKUP
# -------------------------

@app.route("/loyalty", methods=["GET", "POST"])
def loyalty():

    customer = None
    customer_id = None
    error = None
    reward_count = None
    reward_value = None
    remaining_spend = None

    if request.method == "POST":

        customer_id = request.form.get("customer_id", "").strip().upper()

        try:
            id_number = parse_customer_id(customer_id)

            conn = get_connection()
            cursor = conn.cursor()

            cursor.execute(
                f"SELECT forename, surname, points FROM customers WHERE id={p()}",
                (id_number,)
            )

            customer = cursor.fetchone()
            conn.close()

            if customer:
                points = customer[2]

                reward_count = points // 150
                reward_value = reward_count * 2

                remaining_points = 150 - (points % 150)
                if points % 150 == 0:
                    remaining_points = 150

                remaining_spend = remaining_points

            else:
                error = "Customer not found"

        except:
            error = "Invalid ID"

    return render_template(
        "loyalty.html",
        customer=customer,
        customer_id=customer_id,
        error=error,
        reward_count=reward_count,
        reward_value=reward_value,
        remaining_spend=remaining_spend
    )


# -------------------------
# RUN SERVER
# -------------------------

if __name__ == "__main__":
    app.run(debug=True)
