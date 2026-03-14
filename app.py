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

    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT,
            email TEXT UNIQUE,
            password TEXT
        )
    """)

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

    cur.execute("""
        CREATE TABLE IF NOT EXISTS budgets (
            user_id INTEGER PRIMARY KEY,
            monthly_budget REAL
        )
    """)

    db.commit()
    db.close()


init_db()


# ---------------- ANALYTICS FEATURES ---------------- #

def generate_spending_insights(user_id):

    db = get_db()
    cur = db.cursor()

    insights = []

    cur.execute("""
        SELECT category, SUM(amount)
        FROM expenses
        WHERE user_id=?
        GROUP BY category
        ORDER BY SUM(amount) DESC
        LIMIT 1
    """, (user_id,))

    result = cur.fetchone()

    if result:
        insights.append(f"{result[0]} is your highest spending category.")

    cur.execute("""
        SELECT substr(date,1,7), SUM(amount)
        FROM expenses
        WHERE user_id=?
        GROUP BY substr(date,1,7)
        ORDER BY substr(date,1,7) DESC
        LIMIT 2
    """, (user_id,))

    months = cur.fetchall()

    if len(months) == 2:
        if months[0][1] > months[1][1]:
            insights.append("Your spending increased compared to last month.")
        else:
            insights.append("Good job! Your spending decreased compared to last month.")

    db.close()
    return insights


# --------- ONLY CHANGE: RETURN TEXT INSTEAD OF SCORE --------- #

def calculate_financial_health_score(monthly_spent, monthly_budget):

    if not monthly_budget:
        return None

    ratio = monthly_spent / monthly_budget

    if ratio <= 0.5:
        return "Excellent saving"
    elif ratio <= 0.75:
        return "Very healthy"
    elif ratio <= 1:
        return "Acceptable"
    elif ratio <= 1.2:
        return "Risky"
    else:
        return "Poor"


def calculate_recommended_budget(user_id):

    db = get_db()
    cur = db.cursor()

    cur.execute("""
        SELECT substr(date,1,7), SUM(amount)
        FROM expenses
        WHERE user_id=?
        GROUP BY substr(date,1,7)
        ORDER BY substr(date,1,7) DESC
        LIMIT 3
    """, (user_id,))

    months = cur.fetchall()
    db.close()

    if not months:
        return None

    avg_spending = sum(m[1] for m in months) / len(months)

    return round(avg_spending * 1.1, 2)


# ---------------- ROUTES ---------------- #

@app.route("/")
def home():
    return redirect("/login")


# ---------- SIGNUP ---------- #

@app.route("/signup", methods=["GET", "POST"])
def signup():

    if request.method == "POST":

        username = request.form.get("username", "").strip()
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "").strip()

        db = get_db()
        cur = db.cursor()

        try:
            cur.execute(
                "INSERT INTO users (username,email,password) VALUES (?,?,?)",
                (
                    username,
                    email,
                    generate_password_hash(password)
                )
            )
            db.commit()

        except sqlite3.IntegrityError:
            db.close()
            return "Email already registered"

        db.close()

        return redirect("/login")

    return render_template("signup.html")


# ---------- LOGIN ---------- #

@app.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "POST":

        email = request.form.get("email", "").strip()
        password = request.form.get("password", "").strip()

        db = get_db()
        cur = db.cursor()

        cur.execute(
            "SELECT id, username, email, password FROM users WHERE email=?",
            (email,)
        )

        user = cur.fetchone()
        db.close()

        if user and check_password_hash(user[3], password):

            session["user_id"] = user[0]
            session["username"] = user[1]

            return redirect("/dashboard")

        return "Invalid email or password"

    return render_template("login.html")


# ---------- DASHBOARD ---------- #

@app.route("/dashboard")
def dashboard():

    if "user_id" not in session:
        return redirect("/login")

    db = get_db()
    cur = db.cursor()

    cur.execute("""
        SELECT id, amount, category, date, description
        FROM expenses
        WHERE user_id=?
        ORDER BY id DESC
    """, (session["user_id"],))

    expenses = cur.fetchall()

    cur.execute("""
        SELECT SUM(amount)
        FROM expenses
        WHERE user_id=?
        AND substr(date,1,7)=strftime('%Y-%m','now')
    """, (session["user_id"],))

    monthly_spent = cur.fetchone()[0] or 0

    cur.execute("""
        SELECT monthly_budget FROM budgets WHERE user_id=?
    """, (session["user_id"],))

    row = cur.fetchone()
    monthly_budget = row[0] if row else None

    db.close()

    insights = generate_spending_insights(session["user_id"])
    health_score = calculate_financial_health_score(monthly_spent, monthly_budget)
    recommended_budget = calculate_recommended_budget(session["user_id"])

    return render_template(
        "dashboard.html",
        name=session["username"],
        expenses=expenses,
        monthly_spent=monthly_spent,
        monthly_budget=monthly_budget,
        insights=insights,
        health_score=health_score,
        recommended_budget=recommended_budget
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


# ---------- SET BUDGET ---------- #

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


if __name__ == "__main__":
    app.run(debug=True)