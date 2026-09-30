import secrets
import sqlite3
from functools import wraps

from flask import (
    abort, flash, g, redirect, render_template,
    request, session, url_for
)
from werkzeug.security import check_password_hash, generate_password_hash

from db import get_db


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if g.user is None:
            return redirect(url_for("login"))
        return view(*args, **kwargs)

    return wrapped


def register_auth(app):
    @app.before_request
    def load_user_and_check_csrf():
        g.user = None
        user_id = session.get("user_id")

        if user_id is not None:
            g.user = get_db().execute(
                "SELECT id, username FROM users WHERE id = ?",
                (user_id,)
            ).fetchone()

        if "csrf_token" not in session:
            session["csrf_token"] = secrets.token_hex(32)

        if request.method == "POST":
            token = request.form.get("csrf_token", "")

            if not secrets.compare_digest(token, session["csrf_token"]):
                abort(
                    400,
                    description="Your form expired. Reload the page and try again."
                )

    @app.context_processor
    def auth_context():
        return {"csrf_token": session["csrf_token"]}

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if g.user is not None:
            return redirect(url_for("home"))

        username = ""
        action = "login"
        error = None

        if request.method == "POST":
            username = request.form.get("username", "").strip()
            password = request.form.get("password", "")
            action = request.form.get("action", "login")
            conn = get_db()

            if action == "register":
                if not 3 <= len(username) <= 50:
                    error = "Use a username between 3 and 50 characters."

                elif not 8 <= len(password) <= 128:
                    error = "Use a password between 8 and 128 characters."

                elif password != request.form.get("confirm_password"):
                    error = "The passwords do not match."

                else:
                    try:
                        cursor = conn.execute(
                            """
                            INSERT INTO users (username, password_hash)
                            VALUES (?, ?)
                            """,
                            (username, generate_password_hash(password))
                        )
                        conn.commit()
                        user_id = cursor.lastrowid

                    except sqlite3.IntegrityError:
                        conn.rollback()
                        error = "That username is already taken. Choose another."

            elif action == "login":
                user = conn.execute(
                    "SELECT * FROM users WHERE username = ?",
                    (username,)
                ).fetchone()

                if (
                    len(password) > 128
                    or user is None
                    or not user["password_hash"]
                    or not check_password_hash(user["password_hash"], password)
                ):
                    error = "Incorrect username or password."
                else:
                    user_id = user["id"]

            else:
                abort(400)

            if error is None:
                session.clear()
                session["user_id"] = user_id
                session["csrf_token"] = secrets.token_hex(32)

                message = (
                    "Account created. You are logged in."
                    if action == "register"
                    else "You are logged in."
                )
                flash(message, "success")
                return redirect(url_for("home"))

        return render_template(
            "login.html",
            username=username,
            action=action,
            error=error
        )

    @app.post("/logout")
    def logout():
        session.clear()
        flash("You are logged out.", "info")
        return redirect(url_for("login"))