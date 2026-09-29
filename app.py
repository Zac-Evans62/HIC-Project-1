import os
from datetime import date, timedelta

from flask import Flask, render_template

import db
from db import get_db, DEFAULT_USER_ID

app = Flask(__name__)
app.config["SECRET_KEY"] = "change-me-before-submitting"
app.config["DATABASE"] = os.path.join(app.root_path, "platewise.db")
app.teardown_appcontext(db.close_db)

if not os.path.exists(app.config["DATABASE"]):
    with app.app_context():
        db.init_db()


# ---------------------------------------------------------------- HOME
@app.route("/")
def home():
    conn = get_db()
    today = date.today()
    monday = today - timedelta(days=today.weekday())

    # This week's dinners, one entry per day
    week = []
    for i in range(7):
        day = monday + timedelta(days=i)
        recipe = conn.execute(
            "SELECT r.* FROM meal_plan m JOIN recipes r ON r.id = m.recipe_id"
            " WHERE m.user_id = ? AND m.plan_date = ? AND m.meal_slot = 'dinner'"
            " AND r.deleted_at IS NULL",
            (DEFAULT_USER_ID, day.isoformat())).fetchone()
        week.append({"label": day.strftime("%a"), "day_number": day.day,
                     "is_today": day == today, "recipe": recipe})

    tonight = next((d["recipe"] for d in week if d["is_today"]), None)

    favorites = conn.execute(
        "SELECT * FROM recipes WHERE user_id = ? AND is_favorite = 1 AND deleted_at IS NULL"
        " ORDER BY title LIMIT 4", (DEFAULT_USER_ID,)).fetchall()

    return render_template("home.html", tonight=tonight, week=week, favorites=favorites)


# STUB PAGES (teammates replace these)
# just there to make the homepage work
def make_stub(endpoint, url, title):
    def view(**kwargs):
        return render_template("coming_soon.html", page_title=title)
    view.__name__ = endpoint
    app.add_url_rule(url, endpoint, view)


make_stub("login", "/login", "Log in")
make_stub("recipes", "/recipes", "Recipes")
make_stub("recipe_new", "/recipes/new", "New recipe")
make_stub("recipe_detail", "/recipes/<int:recipe_id>", "Recipe")
make_stub("planner", "/planner", "Meal planner")
make_stub("shopping", "/shopping", "Shopping list")
make_stub("cook", "/cook/<int:recipe_id>", "Cooking mode")
make_stub("trash", "/trash", "Trash")


if __name__ == "__main__":
    app.run(debug=True)
