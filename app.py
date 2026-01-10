from flask import Flask, render_template, request, redirect, session, jsonify
import sqlite3
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = "super_secret_key"

# ---------------- DATABASE ---------------- #

def get_db():
    return sqlite3.connect("database.db")

def init_db():
    db = get_db()
    cur = db.cursor()

    # Users
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT,
            email TEXT UNIQUE,
            password TEXT
        )
    """)

    # Expenses
    cur.execute("""
        CREATE TABLE IF NOT EXISTS expenses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            amount REAL,
            category TEXT,
            date TEXT,
            description TEXT
        )
    """)

    # Monthly budget (one per user)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS budgets (
            user_id INTEGER PRIMARY KEY,
            monthly_budget REAL
        )
    """)

    db.commit()
    db.close()

init_db()

# ---------------- ROUTES ---------------- #

@app.route("/")
def home():
    return redirect("/login")

# ---------- SIGNUP ---------- #
@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        db = get_db()
        cur = db.cursor()
        cur.execute(
            "INSERT INTO users (username,email,password) VALUES (?,?,?)",
            (
                request.form["username"],
                request.form["email"],
                generate_password_hash(request.form["password"])
            )
        )
        db.commit()
        db.close()
        return redirect("/login")

    return render_template("signup.html")

# ---------- LOGIN ---------- #
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        db = get_db()
        cur = db.cursor()
        cur.execute(
            "SELECT * FROM users WHERE email=?",
            (request.form["email"],)
        )
        user = cur.fetchone()
        db.close()

        if user and check_password_hash(user[3], request.form["password"]):
            session["user_id"] = user[0]
            session["username"] = user[1]
            return redirect("/dashboard")

    return render_template("login.html")

# ---------- DASHBOARD ---------- #
@app.route("/dashboard")
def dashboard():
    if "user_id" not in session:
        return redirect("/login")

    db = get_db()
    cur = db.cursor()

    # Expenses
    cur.execute("""
        SELECT id, amount, category, date, description
        FROM expenses
        WHERE user_id=?
        ORDER BY id DESC
    """, (session["user_id"],))
    expenses = cur.fetchall()

    # Monthly spent
    cur.execute("""
        SELECT SUM(amount)
        FROM expenses
        WHERE user_id=?
        AND substr(date,1,7)=strftime('%Y-%m','now')
    """, (session["user_id"],))
    monthly_spent = cur.fetchone()[0] or 0

    # Budget
    cur.execute("""
        SELECT monthly_budget FROM budgets WHERE user_id=?
    """, (session["user_id"],))
    row = cur.fetchone()
    monthly_budget = row[0] if row else None

    db.close()

    return render_template(
        "dashboard.html",
        name=session["username"],
        expenses=expenses,
        monthly_spent=monthly_spent,
        monthly_budget=monthly_budget
    )

# ---------- ADD EXPENSE ---------- #
@app.route("/add-expense", methods=["POST"])
def add_expense():
    if "user_id" not in session:
        return redirect("/login")

    db = get_db()
    cur = db.cursor()
    cur.execute("""
        INSERT INTO expenses (user_id, amount, category, date, description)
        VALUES (?, ?, ?, ?, ?)
    """, (
        session["user_id"],
        request.form["amount"],
        request.form["category"],
        request.form["date"],
        request.form["description"]
    ))
    db.commit()
    db.close()

    return redirect("/dashboard")

# ---------- SET / UPDATE BUDGET ---------- #
@app.route("/set-budget", methods=["POST"])
def set_budget():
    if "user_id" not in session:
        return redirect("/login")

    budget = float(request.form["budget"])

    db = get_db()
    cur = db.cursor()
    cur.execute("""
        INSERT INTO budgets (user_id, monthly_budget)
        VALUES (?, ?)
        ON CONFLICT(user_id)
        DO UPDATE SET monthly_budget=excluded.monthly_budget
    """, (session["user_id"], budget))
    db.commit()
    db.close()

    return redirect("/dashboard")

# ---------- CHART DATA ---------- #
@app.route("/chart-data")
def chart_data():
    if "user_id" not in session:
        return jsonify({"categories": [], "months": []})

    db = get_db()
    cur = db.cursor()

    cur.execute("""
        SELECT category, SUM(amount)
        FROM expenses
        WHERE user_id=?
        GROUP BY category
    """, (session["user_id"],))
    categories = cur.fetchall()

    cur.execute("""
        SELECT substr(date,1,7), SUM(amount)
        FROM expenses
        WHERE user_id=?
        GROUP BY substr(date,1,7)
        ORDER BY substr(date,1,7)
    """, (session["user_id"],))
    months = cur.fetchall()

    db.close()

    return jsonify({
        "categories": categories,
        "months": months
    })

# ---------- LOGOUT ---------- #
@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")

# ---------------- RUN ---------------- #
if __name__ == "__main__":
    app.run(debug=True)


