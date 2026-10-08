import os
from datetime import date, timedelta

from flask import Flask, abort, g, render_template, flash, redirect, request, url_for

import db
from db import get_db
from routes.auth import login_required, register_auth
from routes.planner import register_planner
from routes.shopping import register_shopping
from routes.trash import register_trash

import math


app = Flask(__name__)

# Keep a stable local secret so sessions work across app restarts.
os.makedirs(app.instance_path, exist_ok=True)
secret_path = os.path.join(app.instance_path, "secret_key")

if not os.path.exists(secret_path):
    with open(secret_path, "w") as secret_file:
        secret_file.write(os.urandom(32).hex())
    os.chmod(secret_path, 0o600)

with open(secret_path) as secret_file:
    app.config["SECRET_KEY"] = (
        os.environ.get("SECRET_KEY") or secret_file.read().strip()
    )

app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax"
)

app.config["DATABASE"] = os.path.join(app.root_path, "platewise.db")
app.teardown_appcontext(db.close_db)

if not os.path.exists(app.config["DATABASE"]):
    with app.app_context():
        db.init_db()

register_auth(app)
register_planner(app)
register_shopping(app)
register_trash(app)

@app.route("/")
@login_required
def home():
    conn = get_db()
    user_id = g.user["id"]

    today = date.today()
    monday = today - timedelta(days=today.weekday())

    week = []

    for i in range(7):
        day = monday + timedelta(days=i)

        recipe = conn.execute(
            """
            SELECT r.*
            FROM meal_plan m
            JOIN recipes r ON r.id = m.recipe_id
            WHERE m.user_id = ?
              AND m.plan_date = ?
              AND m.meal_slot = 'dinner'
              AND r.deleted_at IS NULL
            """,
            (user_id, day.isoformat())
        ).fetchone()

        week.append({
            "label": day.strftime("%a"),
            "day_number": day.day,
            "is_today": day == today,
            "recipe": recipe
        })

    tonight = next(
        (day["recipe"] for day in week if day["is_today"]),
        None
    )

    favorites = conn.execute(
        """
        SELECT *
        FROM recipes
        WHERE user_id = ?
          AND is_favorite = 1
          AND deleted_at IS NULL
        ORDER BY title
        LIMIT 4
        """,
        (user_id,)
    ).fetchall()

    return render_template(
        "home.html",
        tonight=tonight,
        week=week,
        favorites=favorites
    )


# Teammates can replace these with working feature routes.
def make_stub(endpoint, url, title):
    @login_required
    def view(**kwargs):
        return render_template("coming_soon.html", page_title=title)

    view.__name__ = endpoint
    app.add_url_rule(url, endpoint, view)

make_stub("cook", "/cook/<int:recipe_id>", "Cooking mode")

@app.route("/recipes/new", methods=["GET", "POST"])
@login_required
def recipe_new():
    categories = ["Breakfast", "Lunch", "Dinner", "Dessert", "Snack"]
    errors = []

    # Defaults shown when first opening the form.
    form = {
        "title": "",
        "description": "",
        "category": "Dinner",
        "prep_minutes": "0",
        "cook_minutes": "0",
        "servings": "4",
        "steps": "",
        "is_favorite": False
    }

    ingredient_rows = [
        {"name": "", "quantity": "", "unit": ""}
    ]

    if request.method == "POST":
        for field in (
            "title", "description", "category",
            "prep_minutes", "cook_minutes", "servings", "steps"
        ):
            form[field] = request.form.get(field, "").strip()

        form["is_favorite"] = "is_favorite" in request.form

        names = request.form.getlist("ingredient_name")
        quantities = request.form.getlist("ingredient_quantity")
        units = request.form.getlist("ingredient_unit")

        if not (len(names) == len(quantities) == len(units)):
            errors.append("The ingredient form is incomplete. Please try again.")

        ingredient_rows = [
            {
                "name": name.strip(),
                "quantity": quantity.strip(),
                "unit": unit.strip()
            }
            for name, quantity, unit in zip(names, quantities, units)
        ]

        if not 1 <= len(form["title"]) <= 100:
            errors.append("Enter a recipe name between 1 and 100 characters.")

        if form["category"] not in categories:
            errors.append("Choose a valid category.")

        numbers = {}

        for field, label, minimum in (
            ("prep_minutes", "Preparation time", 0),
            ("cook_minutes", "Cooking time", 0),
            ("servings", "Servings", 1)
        ):
            try:
                value = int(form[field])

                if not minimum <= value <= 10000:
                    raise ValueError

                numbers[field] = value

            except ValueError:
                errors.append(
                    f"{label} must be a whole number from {minimum} to 10,000."
                )

        ingredients = []

        for index, row in enumerate(ingredient_rows, start=1):
            # Ignore completely blank rows.
            if not any(row.values()):
                continue

            if not row["name"]:
                errors.append(f"Enter a name for ingredient {index}.")
                continue

            quantity = None

            if row["quantity"]:
                try:
                    quantity = float(row["quantity"])

                    if not math.isfinite(quantity) or quantity <= 0:
                        raise ValueError

                except ValueError:
                    errors.append(
                        f"Ingredient {index} needs a positive quantity, "
                        "such as 1 or 0.5."
                    )
                    continue

            ingredients.append(
                (row["name"], quantity, row["unit"])
            )

        if not ingredients:
            errors.append("Add at least one ingredient.")

        steps = [
            line.strip()
            for line in form["steps"].splitlines()
            if line.strip()
        ]

        if not steps:
            errors.append("Add at least one cooking step.")

        if not errors:
            conn = get_db()

            # Save everything together. If a write fails, all writes roll back.
            with conn:
                cursor = conn.execute(
                    """
                    INSERT INTO recipes (
                        user_id, title, description, category,
                        prep_minutes, cook_minutes, servings, is_favorite
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        g.user["id"],
                        form["title"],
                        form["description"],
                        form["category"],
                        numbers["prep_minutes"],
                        numbers["cook_minutes"],
                        numbers["servings"],
                        int(form["is_favorite"])
                    )
                )

                recipe_id = cursor.lastrowid

                conn.executemany(
                    """
                    INSERT INTO ingredients (
                        recipe_id, name, quantity, unit
                    )
                    VALUES (?, ?, ?, ?)
                    """,
                    [
                        (recipe_id, name, quantity, unit)
                        for name, quantity, unit in ingredients
                    ]
                )

                conn.executemany(
                    """
                    INSERT INTO steps (
                        recipe_id, position, instruction
                    )
                    VALUES (?, ?, ?)
                    """,
                    [
                        (recipe_id, position, instruction)
                        for position, instruction in enumerate(steps, start=1)
                    ]
                )

            flash(f'Recipe "{form["title"]}" saved.', "success")

            # Return home until the recipe detail page is implemented.
            return redirect(url_for("recipe_detail", recipe_id=recipe_id))

    return render_template(
        "recipe_form.html",
        categories=categories,
        form=form,
        ingredient_rows=ingredient_rows,
        errors=errors
    )

@app.route("/recipes")
@login_required
def recipes():
    search = request.args.get("search", "").strip()
    category = request.args.get("category", "")
    favorites_only = request.args.get("favorites") == "1"

    categories = ["Breakfast", "Lunch", "Dinner", "Dessert", "Snack"]

    query = """
        SELECT *
        FROM recipes
        WHERE user_id = ?
          AND deleted_at IS NULL
    """
    parameters = [g.user["id"]]

    if search:
        # Treat %, _ and backslashes as literal search characters.
        escaped_search = (
            search.replace("\\", "\\\\")
            .replace("%", "\\%")
            .replace("_", "\\_")
        )
        query += " AND title LIKE ? ESCAPE '\\'"
        parameters.append(f"%{escaped_search}%")

    if category in categories:
        query += " AND category = ?"
        parameters.append(category)
    else:
        category = ""

    if favorites_only:
        query += " AND is_favorite = 1"

    query += " ORDER BY title COLLATE NOCASE, id"

    saved_recipes = get_db().execute(
        query, parameters
    ).fetchall()

    return render_template(
        "recipes.html",
        recipes=saved_recipes,
        categories=categories,
        search=search,
        category=category,
        favorites_only=favorites_only
    )


@app.route("/recipes/<int:recipe_id>")
@login_required
def recipe_detail(recipe_id):
    conn = get_db()

    recipe = conn.execute(
        """
        SELECT *
        FROM recipes
        WHERE id = ?
          AND user_id = ?
          AND deleted_at IS NULL
        """,
        (recipe_id, g.user["id"])
    ).fetchone()

    if recipe is None:
        abort(404)

    ingredients = conn.execute(
        """
        SELECT *
        FROM ingredients
        WHERE recipe_id = ?
        ORDER BY id
        """,
        (recipe_id,)
    ).fetchall()

    steps = conn.execute(
        """
        SELECT *
        FROM steps
        WHERE recipe_id = ?
        ORDER BY position, id
        """,
        (recipe_id,)
    ).fetchall()

    return render_template(
        "recipe_detail.html",
        recipe=recipe,
        ingredients=ingredients,
        steps=steps
    )
if __name__ == "__main__":
    app.run(debug=True)