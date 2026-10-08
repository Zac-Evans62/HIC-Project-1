from datetime import date, timedelta

from flask import (
    abort, flash, g, make_response, redirect,
    render_template, request, url_for
)

from db import get_db
from routes.auth import login_required

SLOTS = ("breakfast", "lunch", "dinner")


def parse_date(value):
    try:
        return date.fromisoformat(value or "")
    except ValueError:
        return None


def monday_of(value):
    day = parse_date(value) or date.today()
    return day - timedelta(days=day.weekday())


def load_recipes(conn, user_id):
    return conn.execute(
        "SELECT id, title, category FROM recipes"
        " WHERE user_id = ? AND deleted_at IS NULL ORDER BY title COLLATE NOCASE",
        (user_id,)
    ).fetchall()


def load_meals(conn, user_id, start, end):
    rows = conn.execute(
        """
        SELECT m.id, m.plan_date, m.meal_slot, r.id AS recipe_id, r.title
        FROM meal_plan m JOIN recipes r ON r.id = m.recipe_id
        WHERE m.user_id = ? AND m.plan_date BETWEEN ? AND ?
          AND r.deleted_at IS NULL
        ORDER BY m.id
        """,
        (user_id, start.isoformat(), end.isoformat())
    ).fetchall()
    plan = {}
    for row in rows:
        plan.setdefault((row["plan_date"], row["meal_slot"]), []).append(row)
    return plan


def is_fetch():
    return request.headers.get("X-Requested-With") == "fetch"


def slot_response(conn, day, slot, week_start, error=None, status=200):
    """HTML for one slot so planner.js can update the page without a reload."""
    user_id = g.user["id"]
    meals = load_meals(conn, user_id, day, day).get((day.isoformat(), slot), [])
    html = render_template(
        "partials/_planner_slot.html",
        day=day, slot=slot, slot_meals=meals,
        recipes=load_recipes(conn, user_id),
        week_start=week_start, error=error
    )
    response = make_response(html, status)
    response.headers["X-Planner-Slot"] = "1"
    return response


def register_planner(app):

    @app.route("/planner")
    @login_required
    def planner():
        conn = get_db()
        monday = monday_of(request.args.get("week"))
        days = [monday + timedelta(days=i) for i in range(7)]
        end = days[-1]
        plan = load_meals(conn, g.user["id"], monday, end)
        return render_template(
            "planner.html",
            days=days, slots=SLOTS, plan=plan,
            recipes=load_recipes(conn, g.user["id"]),
            today=date.today(),
            week_start=monday.isoformat(),
            week_label=f"{monday:%b} {monday.day} to {end:%b} {end.day}, {end.year}",
            prev_week=(monday - timedelta(days=7)).isoformat(),
            next_week=(monday + timedelta(days=7)).isoformat(),
            is_this_week=monday == monday_of(None),
            planned=len(plan), total=len(days) * len(SLOTS), error=None
        )

    @app.post("/planner/add")
    @login_required
    def planner_add():
        conn = get_db()
        user_id = g.user["id"]
        day = parse_date(request.form.get("plan_date"))
        slot = request.form.get("meal_slot")
        week_start = monday_of(request.form.get("week")).isoformat()
        if day is None or slot not in SLOTS:
            abort(400)

        error = None
        recipe = None
        recipe_id = request.form.get("recipe_id", type=int)
        if recipe_id is None:
            error = "Choose a recipe first."
        else:
            recipe = conn.execute(
                "SELECT id, title FROM recipes"
                " WHERE id = ? AND user_id = ? AND deleted_at IS NULL",
                (recipe_id, user_id)
            ).fetchone()
            if recipe is None:
                error = "That recipe is no longer available. Pick another one."

        if error is None:
            taken = conn.execute(
                "SELECT 1 FROM meal_plan WHERE user_id = ? AND plan_date = ? AND meal_slot = ?",
                (user_id, day.isoformat(), slot)
            ).fetchone()
            if taken:
                error = "This slot already has a meal. Remove it first to pick another."

        if error is None:
            with conn:
                conn.execute(
                    "INSERT INTO meal_plan (user_id, recipe_id, plan_date, meal_slot)"
                    " VALUES (?, ?, ?, ?)",
                    (user_id, recipe["id"], day.isoformat(), slot)
                )

        if is_fetch():
            return slot_response(conn, day, slot, week_start, error, 400 if error else 200)

        if error:
            flash(error, "error")
        else:
            flash(f'Added "{recipe["title"]}" to {day:%A} {slot}.', "success")
        return redirect(url_for("planner", week=week_start))

    @app.post("/planner/remove/<int:meal_id>")
    @login_required
    def planner_remove(meal_id):
        conn = get_db()
        meal = conn.execute(
            """
            SELECT m.id, m.plan_date, m.meal_slot, r.title
            FROM meal_plan m JOIN recipes r ON r.id = m.recipe_id
            WHERE m.id = ? AND m.user_id = ?
            """,
            (meal_id, g.user["id"])
        ).fetchone()
        if meal is None:
            abort(404)

        with conn:
            conn.execute("DELETE FROM meal_plan WHERE id = ?", (meal_id,))

        day = parse_date(meal["plan_date"])
        week_start = monday_of(request.form.get("week")).isoformat()
        if is_fetch():
            return slot_response(conn, day, meal["meal_slot"], week_start)

        flash(f'Removed "{meal["title"]}" from {day:%A} {meal["meal_slot"]}.', "info")
        return redirect(url_for("planner", week=week_start))

    @app.post("/planner/repeat")
    @login_required
    def planner_repeat():
        """Copy last week's meals into this week's EMPTY slots only."""
        conn = get_db()
        user_id = g.user["id"]
        monday = monday_of(request.form.get("week"))
        last_monday = monday - timedelta(days=7)

        last_week = conn.execute(
            """
            SELECT m.plan_date, m.meal_slot, m.recipe_id
            FROM meal_plan m JOIN recipes r ON r.id = m.recipe_id
            WHERE m.user_id = ? AND m.plan_date BETWEEN ? AND ?
              AND r.deleted_at IS NULL
            ORDER BY m.id
            """,
            (user_id, last_monday.isoformat(), (last_monday + timedelta(days=6)).isoformat())
        ).fetchall()

        if not last_week:
            flash("Last week has no meals to copy.", "info")
            return redirect(url_for("planner", week=monday.isoformat()))

        filled = set(load_meals(conn, user_id, monday, monday + timedelta(days=6)))
        copied = 0
        with conn:
            for row in last_week:
                source = parse_date(row["plan_date"])
                if source is None:
                    continue
                target = (source + timedelta(days=7)).isoformat()
                if (target, row["meal_slot"]) in filled:
                    continue
                conn.execute(
                    "INSERT INTO meal_plan (user_id, recipe_id, plan_date, meal_slot)"
                    " VALUES (?, ?, ?, ?)",
                    (user_id, row["recipe_id"], target, row["meal_slot"])
                )
                filled.add((target, row["meal_slot"]))
                copied += 1

        if copied:
            flash(f"Copied {copied} {'meal' if copied == 1 else 'meals'} from last week.", "success")
        else:
            flash("Every slot this week already has a meal, so nothing was copied.", "info")
        return redirect(url_for("planner", week=monday.isoformat()))
