from flask import Flask, render_template, request
import sqlite3
import qrcode

app = Flask(__name__)

# -------------------------
# DATABASE INITIALISATION
# -------------------------

def init_db():
    conn = sqlite3.connect("customers.db")
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
    return render_template("welcome.html")


# -------------------------
# SIGNUP
# -------------------------

@app.route("/signup", methods=["GET","POST"])
def signup():

    if request.method == "POST":

        forename = request.form["forename"]
        surname = request.form["surname"]
        phone = request.form["phone"]
        email = request.form["email"]

        conn = sqlite3.connect("customers.db")
        cursor = conn.cursor()

        cursor.execute("""
        INSERT INTO customers(forename,surname,phone,email)
        VALUES(?,?,?,?)
        """,(forename,surname,phone,email))

        customer_id = cursor.lastrowid

        conn.commit()
        conn.close()

        formatted_id = "NP" + str(customer_id).zfill(5)

        qr = qrcode.make(formatted_id)
        qr.save(f"static/qrcodes/qr_{formatted_id}.png")

        return render_template(
            "welcome.html",
            forename=forename,
            customer_id=formatted_id
        )

    return render_template("signup.html")


# -------------------------
# SCAN CUSTOMER
# -------------------------

@app.route("/scan", methods=["GET","POST"])
def scan():

    customer = None
    customer_id = None
    error = None

    if request.method == "POST":

        customer_id = request.form.get("customer_id","").strip().upper()

        if customer_id == "":
            error = "Please scan or enter a customer ID"
            return render_template("scan.html", error=error)

        try:
            if customer_id.startswith("NP"):
                id_number = int(customer_id[2:])
            else:
                id_number = int(customer_id)

            conn = sqlite3.connect("customers.db")
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

    # 🐠 Get amounts (handle empty + comma)
    fish_amount = request.form.get("fish_amount", "0").replace(",", ".")
    other_amount = request.form.get("other_amount", "0").replace(",", ".")

    # Convert safely
    fish_amount = float(fish_amount) if fish_amount else 0
    other_amount = float(other_amount) if other_amount else 0

    # 🎯 Points logic
    fish_points = int(fish_amount * 2)     # double points for fish
    other_points = int(other_amount)       # normal points

    points = fish_points + other_points
    total_amount = fish_amount + other_amount

    # Extract numeric ID
    id_number = int(customer_id[2:])

    conn = sqlite3.connect("customers.db")
    cursor = conn.cursor()

    # Update total points
    cursor.execute(
        "UPDATE customers SET points = points + ? WHERE id=?",
        (points, id_number)
    )

    # Save transaction
    cursor.execute(
        "INSERT INTO transactions (customer_id, points, amount, reason) VALUES (?,?,?,?)",
        (id_number, points, total_amount, "Purchase")
    )

    # Get updated customer
    cursor.execute(
        "SELECT forename, surname, points FROM customers WHERE id=?",
        (id_number,)
    )

    customer = cursor.fetchone()

    conn.commit()
    conn.close()

    # 🎁 Reward check
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
    id_number = int(customer_id[2:])

    conn = sqlite3.connect("customers.db")
    cursor = conn.cursor()

    cursor.execute(
        "SELECT points FROM customers WHERE id=?",
        (id_number,)
    )

    current_points = cursor.fetchone()[0]

    if current_points >= 150:

        cursor.execute(
            "UPDATE customers SET points = points - 150 WHERE id=?",
            (id_number,)
        )

        cursor.execute(
            "INSERT INTO transactions (customer_id, points, amount, reason) VALUES (?,?,?,?)",
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

    numeric_id = int(customer_id.replace("NP", ""))

    conn = sqlite3.connect("customers.db")
    cursor = conn.cursor()

    cursor.execute("""
        SELECT points, amount, reason, timestamp
        FROM transactions
        WHERE customer_id = ?
        ORDER BY timestamp DESC
    """, (numeric_id,))

    transactions = cursor.fetchall()

    conn.close()

    return render_template(
        "history.html",
        transactions=transactions,
        customer_id=customer_id
    )

@app.route("/redeem_custom", methods=["POST"])
def redeem_custom():

    customer_id = request.form["customer_id"]
    redeem_value = int(request.form["redeem_value"])  # £ value

    id_number = int(customer_id[2:])

    conn = sqlite3.connect("customers.db")
    cursor = conn.cursor()

    cursor.execute(
        "SELECT forename, surname, points FROM customers WHERE id=?",
        (id_number,)
    )

    customer = cursor.fetchone()
    current_points = customer[2]

    # Convert £ → points
    points_to_deduct = (redeem_value // 2) * 150

    if current_points >= points_to_deduct:

        cursor.execute(
            "UPDATE customers SET points = points - ? WHERE id=?",
            (points_to_deduct, id_number)
        )

        cursor.execute(
            "INSERT INTO transactions (customer_id, points, amount, reason) VALUES (?,?,?,?)",
            (id_number, -points_to_deduct, -redeem_value, "Reward redeemed")
        )

        conn.commit()

        new_points = current_points - points_to_deduct
        message = f"£{redeem_value} reward applied"

    else:
        new_points = current_points
        message = "Not enough points"

    conn.close()

    # Recalculate rewards
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
@app.route("/loyalty", methods=["GET", "POST"])
def loyalty():

    customer = None
    customer_id = None
    error = None

    if request.method == "POST":

        customer_id = request.form.get("customer_id", "").strip().upper()

        try:
            if customer_id.startswith("NP"):
                id_number = int(customer_id[2:])
            else:
                id_number = int(customer_id)

            conn = sqlite3.connect("customers.db")
            cursor = conn.cursor()

            cursor.execute(
                "SELECT forename, surname, points FROM customers WHERE id=?",
                (id_number,)
            )

            customer = cursor.fetchone()
            conn.close()

            if customer:
                points = customer[2]

                reward_count = points // 150
                reward_value = reward_count * 2

                remaining_points = 150 - (points % 150)
                remaining_spend = remaining_points  # £1 = 1 point

            else:
                error = "Customer not found"

        except:
            error = "Invalid ID"

    return render_template(
        "loyalty.html",
        customer=customer,
        customer_id=customer_id,
        error=error,
        reward_count=locals().get("reward_count"),
        reward_value=locals().get("reward_value"),
        remaining_spend=locals().get("remaining_spend")
    )    
# -------------------------
# RUN SERVER
# -------------------------

if __name__ == "__main__":
    app.run(debug=True)
