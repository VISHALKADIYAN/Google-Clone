import os
import re
import sqlite3
from functools import wraps
from urllib.parse import quote_plus

from flask import (
    Flask, render_template, request, redirect, url_for,
    flash, session, g, jsonify
)
from werkzeug.security import generate_password_hash, check_password_hash

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DATABASE = os.path.join(BASE_DIR, "instance", "google_clone.db")

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-only-change-this-secret-key")
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"


def get_db():
    if "db" not in g:
        os.makedirs(os.path.dirname(DATABASE), exist_ok=True)
        g.db = sqlite3.connect(DATABASE)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


@app.teardown_appcontext
def close_db(exception=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    with app.app_context():
        db = get_db()
        db.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                email TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS searches (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                query TEXT NOT NULL,
                searched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
            );
            CREATE INDEX IF NOT EXISTS idx_searches_user_id
                ON searches(user_id, searched_at DESC);
        """)
        db.commit()


@app.before_request
def load_logged_in_user():
    user_id = session.get("user_id")
    g.user = None
    if user_id is not None:
        g.user = get_db().execute(
            "SELECT id, username, email FROM users WHERE id = ?", (user_id,)
        ).fetchone()
        if g.user is None:
            session.clear()


def login_required(view):
    @wraps(view)
    def wrapped_view(*args, **kwargs):
        if g.user is None:
            flash("Please log in to view that page.", "info")
            return redirect(url_for("login", next=request.path))
        return view(*args, **kwargs)
    return wrapped_view


def valid_email(email):
    return bool(re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email))


@app.route("/")
def index():
    recent = []
    if g.user:
        recent = get_db().execute(
            "SELECT query FROM searches WHERE user_id = ? "
            "GROUP BY query ORDER BY MAX(searched_at) DESC LIMIT 5",
            (g.user["id"],)
        ).fetchall()
    return render_template("index.html", recent=recent)


@app.route("/register", methods=["GET", "POST"])
def register():
    if g.user:
        return redirect(url_for("index"))
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        confirm = request.form.get("confirm_password", "")
        error = None

        if len(username) < 3 or len(username) > 30:
            error = "Username must be between 3 and 30 characters."
        elif not re.fullmatch(r"[A-Za-z0-9_.-]+", username):
            error = "Username can use letters, numbers, dots, underscores and hyphens."
        elif not valid_email(email):
            error = "Enter a valid email address."
        elif len(password) < 8:
            error = "Password must contain at least 8 characters."
        elif password != confirm:
            error = "Passwords do not match."

        if error:
            flash(error, "error")
        else:
            db = get_db()
            try:
                db.execute(
                    "INSERT INTO users (username, email, password_hash) VALUES (?, ?, ?)",
                    (username, email, generate_password_hash(password))
                )
                db.commit()
                flash("Account created. You can now log in.", "success")
                return redirect(url_for("login"))
            except sqlite3.IntegrityError:
                flash("That username or email is already registered.", "error")

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if g.user:
        return redirect(url_for("index"))
    if request.method == "POST":
        identity = request.form.get("identity", "").strip()
        password = request.form.get("password", "")
        user = get_db().execute(
            "SELECT * FROM users WHERE username = ? COLLATE NOCASE OR email = ? COLLATE NOCASE",
            (identity, identity)
        ).fetchone()
        if user is None or not check_password_hash(user["password_hash"], password):
            flash("Incorrect username/email or password.", "error")
        else:
            session.clear()
            session["user_id"] = user["id"]
            flash(f"Welcome back, {user['username']}!", "success")
            next_url = request.args.get("next", "")
            if next_url.startswith("/") and not next_url.startswith("//"):
                return redirect(next_url)
            return redirect(url_for("index"))
    return render_template("login.html")


@app.route("/logout", methods=["POST"])
def logout():
    session.clear()
    flash("You have been logged out.", "info")
    return redirect(url_for("index"))


@app.route("/search")
def search():
    query = request.args.get("q", "").strip()
    category = request.args.get("type", "web").strip().lower()
    allowed = {"web", "images", "news", "videos", "maps"}
    if category not in allowed:
        category = "web"
    if not query:
        flash("Please enter a search query.", "info")
        return redirect(url_for("index"))

    query = query[:300]
    if g.user:
        db = get_db()
        db.execute(
            "INSERT INTO searches (user_id, query) VALUES (?, ?)",
            (g.user["id"], query)
        )
        db.commit()

    encoded = quote_plus(query)
    destinations = {
        "web": f"https://www.google.com/search?q={encoded}",
        "images": f"https://www.google.com/search?tbm=isch&q={encoded}",
        "news": f"https://www.google.com/search?tbm=nws&q={encoded}",
        "videos": f"https://www.google.com/search?tbm=vid&q={encoded}",
        "maps": f"https://www.google.com/maps/search/{encoded}",
    }
    return render_template(
        "results.html", query=query, category=category,
        destination=destinations[category]
    )


@app.route("/history")
@login_required
def history():
    searches = get_db().execute(
        "SELECT id, query, searched_at FROM searches "
        "WHERE user_id = ? ORDER BY searched_at DESC LIMIT 200",
        (g.user["id"],)
    ).fetchall()
    return render_template("history.html", searches=searches)


@app.route("/history/delete", methods=["POST"])
@login_required
def delete_history():
    get_db().execute("DELETE FROM searches WHERE user_id = ?", (g.user["id"],))
    get_db().commit()
    flash("Your search history has been deleted.", "success")
    return redirect(url_for("history"))


@app.route("/api/suggestions")
def suggestions():
    q = request.args.get("q", "").strip()[:100]
    if not q:
        return jsonify([])
    # Suggestions are based on this app's own history, not Google's private autocomplete service.
    rows = get_db().execute(
        "SELECT query, MAX(searched_at) AS latest FROM searches "
        "WHERE query LIKE ? GROUP BY query ORDER BY latest DESC LIMIT 6",
        (f"%{q}%",)
    ).fetchall()
    return jsonify([row["query"] for row in rows])


@app.errorhandler(404)
def not_found(error):
    return render_template("error.html", code=404, message="Page not found."), 404


@app.errorhandler(500)
def server_error(error):
    return render_template(
        "error.html", code=500, message="Something went wrong. Please try again."
    ), 500


if __name__ == "__main__":
    init_db()
    app.run(debug=os.environ.get("FLASK_DEBUG", "1") == "1")
