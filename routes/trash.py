from datetime import datetime

from flask import abort, flash, g, redirect, request, session, url_for, render_template

from db import get_db
from routes.auth import login_required


def when(value):
    """'2026-10-08T13:41:00' -> 'Oct 8, 2026'."""
    try:
        moment = datetime.fromisoformat(value)
        return f"{moment:%b} {moment.day}, {moment.year}"
    except (TypeError, ValueError):
        return value or ""


def purge(conn, recipe_ids):
    """Permanently remove recipes and everything that points at them."""
    for recipe_id in recipe_ids:
        conn.execute("DELETE FROM meal_plan WHERE recipe_id = ?", (recipe_id,))
        conn.execute("DELETE FROM ingredients WHERE recipe_id = ?", (recipe_id,))
        conn.execute("DELETE FROM steps WHERE recipe_id = ?", (recipe_id,))
        conn.execute("DELETE FROM recipes WHERE id = ?", (recipe_id,))


def register_trash(app):

    @app.context_processor
    def trash_undo_context():
        # Shown once, on the first full page after a recipe is moved to Trash.
        return {"trash_undo": session.pop("trash_undo", None)}

    @app.route("/trash")
    @login_required
    def trash():
        conn = get_db()
        user_id = g.user["id"]

        planned = dict(conn.execute(
            "SELECT recipe_id, COUNT(*) FROM meal_plan WHERE user_id = ? GROUP BY recipe_id",
            (user_id,)
        ).fetchall())

        recipes = []
        for row in conn.execute(
            "SELECT id, title, description, category, prep_minutes, cook_minutes,"
            " servings, is_favorite, deleted_at FROM recipes"
            " WHERE user_id = ? AND deleted_at IS NOT NULL"
            " ORDER BY deleted_at DESC, id DESC",
            (user_id,)
        ):
            recipe = dict(row)
            recipe["deleted_label"] = when(row["deleted_at"])
            recipe["planned"] = planned.get(row["id"], 0)
            recipes.append(recipe)

        return render_template("trash.html", recipes=recipes)

    @app.post("/recipes/<int:recipe_id>/delete")
    @login_required
    def recipe_delete(recipe_id):
        """Move a recipe to Trash. Nothing is erased, so Undo and Restore both work."""
        conn = get_db()
        recipe = conn.execute(
            "SELECT id, title FROM recipes"
            " WHERE id = ? AND user_id = ? AND deleted_at IS NULL",
            (recipe_id, g.user["id"])
        ).fetchone()
        if recipe is None:
            abort(404)

        with conn:
            conn.execute(
                "UPDATE recipes SET deleted_at = ? WHERE id = ?",
                (datetime.now().isoformat(timespec="seconds"), recipe_id)
            )

        session["trash_undo"] = {"id": recipe["id"], "title": recipe["title"]}
        return redirect(url_for("recipes"))

    @app.post("/trash/restore/<int:recipe_id>")
    @login_required
    def trash_restore(recipe_id):
        conn = get_db()
        recipe = conn.execute(
            "SELECT id, title FROM recipes"
            " WHERE id = ? AND user_id = ? AND deleted_at IS NOT NULL",
            (recipe_id, g.user["id"])
        ).fetchone()
        if recipe is None:
            abort(404)

        with conn:
            conn.execute("UPDATE recipes SET deleted_at = NULL WHERE id = ?", (recipe_id,))

        flash(f'Restored "{recipe["title"]}".', "success")
        if request.form.get("next") == "recipe":
            return redirect(url_for("recipe_detail", recipe_id=recipe_id))
        return redirect(url_for("trash"))

    @app.post("/trash/delete/<int:recipe_id>")
    @login_required
    def trash_delete(recipe_id):
        conn = get_db()
        recipe = conn.execute(
            "SELECT id, title FROM recipes"
            " WHERE id = ? AND user_id = ? AND deleted_at IS NOT NULL",
            (recipe_id, g.user["id"])
        ).fetchone()
        if recipe is None:
            abort(404)

        with conn:
            purge(conn, [recipe_id])

        flash(f'Permanently deleted "{recipe["title"]}".', "info")
        return redirect(url_for("trash"))

    @app.post("/trash/empty")
    @login_required
    def trash_empty():
        conn = get_db()
        ids = [row["id"] for row in conn.execute(
            "SELECT id FROM recipes WHERE user_id = ? AND deleted_at IS NOT NULL",
            (g.user["id"],)
        )]

        if not ids:
            flash("Trash is already empty.", "info")
        else:
            with conn:
                purge(conn, ids)
            flash(f"Permanently deleted {len(ids)} {'recipe' if len(ids) == 1 else 'recipes'}.", "info")
        return redirect(url_for("trash"))
