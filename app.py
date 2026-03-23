from flask import Flask, render_template, request, session, redirect, url_for
import sqlite3
import qrcode
import os

app = Flask(__name__)

# -------------------------
# SECRET KEY (FROM ENV)
# -------------------------
app.secret_key = os.getenv("SECRET_KEY", "fallback-secret")

# -------------------------
# CONFIG
# -------------------------

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SQLITE_PATH = os.path.join(BASE_DIR, "customers.db")
QR_DIR = os.path.join(BASE_DIR, "static", "qrcodes")

STAFF_USERNAME = os.getenv("STAFF_USERNAME", "admin")
STAFF_PASSWORD = os.getenv("STAFF_PASSWORD", "newport1003!")

# -------------------------
# DATABASE
# -------------------------

def get_connection():
    return sqlite3.connect(SQLITE_PATH)


def parse_customer_id(customer_id):
    customer_id = customer_id.strip().upper()
    if customer_id.startswith("NP"):
        return int(customer_id[2:])
    return int(customer_id)


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

        cursor.execute("""
        INSERT INTO customers(forename, surname, phone, email)
        VALUES(?, ?, ?, ?)
        """, (forename, surname, phone, email))

        customer_id = cursor.lastrowid

        conn.commit()
        conn.close()

        formatted_id = "NP" + str(customer_id).zfill(5)

        # ✅ CREATE QR FOLDER ONLY WHEN NEEDED
        os.makedirs(QR_DIR, exist_ok=True)

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

    if not session.get("logged_in"):
        return redirect("/login")

    customer = None
    error = None
    customer_id = None

    if request.method == "POST":

        customer_id = request.form.get("customer_id", "").strip().upper()

        if customer_id == "":
            error = "Please scan or enter ID"
            return render_template("scan.html", error=error)

        try:
            id_number = parse_customer_id(customer_id)

            conn = get_connection()
            cursor = conn.cursor()

            cursor.execute(
                "SELECT id, forename, surname, points FROM customers WHERE id=?",
                (id_number,)
            )

            customer = cursor.fetchone()
            conn.close()

            if not customer:
                error = "Customer not found"

        except:
            error = "Invalid ID"

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
        "UPDATE customers SET points = points + ? WHERE id=?",
        (points, id_number)
    )

    cursor.execute(
        "INSERT INTO transactions (customer_id, points, amount, reason) VALUES (?, ?, ?, ?)",
        (id_number, points, total_amount, "Purchase")
    )

    cursor.execute(
        "SELECT forename, surname, points FROM customers WHERE id=?",
        (id_number,)
    )

    customer = cursor.fetchone()

    conn.commit()
    conn.close()

    new_points = customer[2]

    return render_template(
        "points_added.html",
        forename=customer[0],
        surname=customer[1],
        customer_id=customer_id,
        points_added=points,
        new_points=new_points
    )


# -------------------------
# RUN
# -------------------------

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
