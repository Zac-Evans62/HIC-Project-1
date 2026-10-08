from flask import (
    abort, flash, g, jsonify, redirect,
    render_template, request, url_for
)

from db import get_db
from routes.auth import login_required
from routes.planner import is_fetch, monday_of
from datetime import timedelta

# Columns the shopping list needs on top of the original shopping_items table.
NEW_COLUMNS = (
    ("week_start", "TEXT"),
    ("unit", "TEXT"),
    ("item_key", "TEXT"),
    ("is_extra", "INTEGER DEFAULT 0"),
)


def ensure_columns(app):
    """Add the new columns if they are missing, so nobody has to reset the database."""
    with app.app_context():
        conn = get_db()
        existing = {row["name"] for row in conn.execute("PRAGMA table_info(shopping_items)")}
        for name, definition in NEW_COLUMNS:
            if name not in existing:
                conn.execute(f"ALTER TABLE shopping_items ADD COLUMN {name} {definition}")
        conn.commit()


def normalize(text):
    """Lowercase, trim and drop a trailing 's' so 'Apples' and 'apple' match."""
    text = " ".join((text or "").lower().split())
    if len(text) > 2 and text.endswith("s") and not text.endswith("ss"):
        text = text[:-1]
    return text


def quantity_text(item):
    if item["quantity"] is None:
        return ""
    return f'{item["quantity"]:g} {item["unit"]}'.strip()


def build_needed(conn, user_id, monday):
    """Add up the ingredients of every meal planned for the week."""
    rows = conn.execute(
        """
        SELECT r.title, i.name, i.quantity, i.unit
        FROM meal_plan m
        JOIN recipes r ON r.id = m.recipe_id
        JOIN ingredients i ON i.recipe_id = r.id
        WHERE m.user_id = ? AND m.plan_date BETWEEN ? AND ?
          AND r.deleted_at IS NULL
        ORDER BY m.plan_date, m.id, i.id
        """,
        (user_id, monday.isoformat(), (monday + timedelta(days=6)).isoformat())
    ).fetchall()

    needed = {}
    for row in rows:
        name = (row["name"] or "").strip()
        if not name:
            continue
        unit = (row["unit"] or "").strip()
        key = (normalize(name), normalize(unit))
        item = needed.setdefault(
            key, {"name": name, "unit": unit, "quantity": None, "recipes": []}
        )
        if row["quantity"] is not None:
            item["quantity"] = (item["quantity"] or 0) + row["quantity"]
        if row["title"] not in item["recipes"]:
            item["recipes"].append(row["title"])
    return needed


def sync_week(conn, user_id, monday):
    """Make the saved rows match the current plan, keeping check marks for items still needed."""
    week = monday.isoformat()
    needed = build_needed(conn, user_id, monday)

    existing = {
        (row["item_key"], row["unit"]): row
        for row in conn.execute(
            "SELECT id, name, quantity, item_key, unit FROM shopping_items"
            " WHERE user_id = ? AND week_start = ? AND is_extra = 0",
            (user_id, week)
        )
    }

    with conn:
        for key, item in needed.items():
            text = quantity_text(item)
            row = existing.pop(key, None)
            if row is None:
                conn.execute(
                    "INSERT INTO shopping_items"
                    " (user_id, name, quantity, checked, week_start, unit, item_key, is_extra)"
                    " VALUES (?, ?, ?, 0, ?, ?, ?, 0)",
                    (user_id, item["name"], text, week, key[1], key[0])
                )
            elif row["name"] != item["name"] or row["quantity"] != text:
                conn.execute(
                    "UPDATE shopping_items SET name = ?, quantity = ? WHERE id = ?",
                    (item["name"], text, row["id"])
                )
        # Anything left over is no longer in the plan.
        for row in existing.values():
            conn.execute("DELETE FROM shopping_items WHERE id = ?", (row["id"],))

    return needed


def render_list(conn, monday, error=None, form=None, status=200):
    user_id = g.user["id"]
    week = monday.isoformat()
    needed = sync_week(conn, user_id, monday)

    rows = conn.execute(
        "SELECT * FROM shopping_items WHERE user_id = ? AND week_start = ?"
        " ORDER BY name COLLATE NOCASE, id",
        (user_id, week)
    ).fetchall()

    items, extras = [], []
    for row in rows:
        item = dict(row)
        if row["is_extra"]:
            extras.append(item)
        else:
            item["recipes"] = needed.get((row["item_key"], row["unit"]), {}).get("recipes", [])
            items.append(item)

    total = len(rows)
    done = sum(1 for row in rows if row["checked"])
    end = monday + timedelta(days=6)

    meal_count = conn.execute(
        "SELECT COUNT(*) FROM meal_plan m JOIN recipes r ON r.id = m.recipe_id"
        " WHERE m.user_id = ? AND m.plan_date BETWEEN ? AND ? AND r.deleted_at IS NULL",
        (user_id, week, end.isoformat())
    ).fetchone()[0]

    html = render_template(
        "shopping.html",
        items=items, extras=extras, total=total, done=done,
        percent=(done * 100 // total) if total else 0,
        meal_count=meal_count,
        week_start=week,
        week_label=f"{monday:%b} {monday.day} to {end:%b} {end.day}, {end.year}",
        prev_week=(monday - timedelta(days=7)).isoformat(),
        next_week=(monday + timedelta(days=7)).isoformat(),
        is_this_week=monday == monday_of(None),
        error=error,
        form=form or {"name": "", "quantity": ""}
    )
    return html, status


def register_shopping(app):
    ensure_columns(app)

    @app.route("/shopping")
    @login_required
    def shopping():
        monday = monday_of(request.args.get("week"))
        return render_list(get_db(), monday)

    @app.post("/shopping/toggle/<int:item_id>")
    @login_required
    def shopping_toggle(item_id):
        conn = get_db()
        item = conn.execute(
            "SELECT id, week_start FROM shopping_items WHERE id = ? AND user_id = ?",
            (item_id, g.user["id"])
        ).fetchone()
        if item is None:
            abort(404)

        checked = 1 if "checked" in request.form else 0
        with conn:
            conn.execute("UPDATE shopping_items SET checked = ? WHERE id = ?", (checked, item_id))

        if is_fetch():
            return jsonify(ok=True, checked=bool(checked))
        return redirect(url_for("shopping", week=item["week_start"]))

    @app.post("/shopping/add")
    @login_required
    def shopping_add():
        conn = get_db()
        monday = monday_of(request.form.get("week"))
        name = request.form.get("name", "").strip()
        quantity = request.form.get("quantity", "").strip()

        error = None
        if not name:
            error = "Enter the name of the item you want to add."
        elif len(name) > 60:
            error = "Item names can be up to 60 characters."
        elif len(quantity) > 30:
            error = "Quantity can be up to 30 characters, such as 2 packs."

        if error:
            if is_fetch():
                return jsonify(ok=False, error=error), 400
            return render_list(conn, monday, error, {"name": name, "quantity": quantity}, 400)

        with conn:
            conn.execute(
                "INSERT INTO shopping_items"
                " (user_id, name, quantity, checked, week_start, unit, item_key, is_extra)"
                " VALUES (?, ?, ?, 0, ?, '', '', 1)",
                (g.user["id"], name, quantity, monday.isoformat())
            )

        if is_fetch():
            return jsonify(ok=True)
        flash(f'Added "{name}" to your list.', "success")
        return redirect(url_for("shopping", week=monday.isoformat()))

    @app.post("/shopping/remove/<int:item_id>")
    @login_required
    def shopping_remove(item_id):
        conn = get_db()
        item = conn.execute(
            "SELECT id, name, week_start FROM shopping_items"
            " WHERE id = ? AND user_id = ? AND is_extra = 1",
            (item_id, g.user["id"])
        ).fetchone()
        if item is None:
            abort(404)

        with conn:
            conn.execute("DELETE FROM shopping_items WHERE id = ?", (item_id,))

        if is_fetch():
            return jsonify(ok=True)
        flash(f'Removed "{item["name"]}" from your list.', "info")
        return redirect(url_for("shopping", week=item["week_start"]))

    @app.post("/shopping/reset")
    @login_required
    def shopping_reset():
        conn = get_db()
        monday = monday_of(request.form.get("week"))
        with conn:
            cursor = conn.execute(
                "UPDATE shopping_items SET checked = 0"
                " WHERE user_id = ? AND week_start = ? AND checked = 1",
                (g.user["id"], monday.isoformat())
            )
        count = cursor.rowcount
        if count:
            flash(f"Unchecked {count} {'item' if count == 1 else 'items'}.", "info")
        else:
            flash("No items were checked.", "info")
        return redirect(url_for("shopping", week=monday.isoformat()))
