import sqlite3
from datetime import date, timedelta
from flask import g, current_app

DEFAULT_USER_ID = 1  # until real login is added, everyone is the "guest" user


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(current_app.config["DATABASE"])
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


def close_db(e=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    """Create all tables from schema.sql and fill them with sample data."""
    db = get_db()
    with current_app.open_resource("schema.sql") as f:
        db.executescript(f.read().decode("utf8"))
    seed_db(db)
    db.commit()


# (title, category, description, prep, cook, servings, favorite,
#  [(ingredient, qty, unit)], [steps])
SAMPLE_RECIPES = [
    ("Pumpkin Pancakes", "Breakfast", "Fluffy pancakes with warm autumn spices.", 10, 15, 4, 1,
     [("Flour", 1.5, "cup"), ("Pumpkin puree", 0.5, "cup"), ("Milk", 1, "cup"), ("Cinnamon", 1, "tsp")],
     ["Whisk the dry ingredients together.", "Stir in pumpkin and milk until just combined.",
      "Cook spoonfuls on a hot buttered pan until golden on both sides."]),
    ("Butternut Squash Soup", "Dinner", "Creamy roasted squash soup.", 15, 40, 4, 1,
     [("Butternut squash", 1, ""), ("Onion", 1, ""), ("Vegetable broth", 4, "cup"), ("Cream", 0.5, "cup")],
     ["Roast the cubed squash at 400F for 30 minutes.", "Saute the onion, add squash and broth, simmer 10 minutes.",
      "Blend until smooth and stir in the cream."]),
    ("Chicken Pot Pie", "Dinner", "Golden crust over a hearty filling.", 25, 45, 6, 1,
     [("Chicken breast", 2, "lb"), ("Mixed vegetables", 2, "cup"), ("Pie crust", 2, ""), ("Chicken broth", 1, "cup")],
     ["Cook and shred the chicken.", "Mix chicken, vegetables and broth in the bottom crust.",
      "Cover with the top crust and bake at 375F for 40 minutes."]),
    ("Apple Cinnamon Oatmeal", "Breakfast", "A cozy bowl for cold mornings.", 5, 10, 2, 0,
     [("Rolled oats", 1, "cup"), ("Apple", 1, ""), ("Milk", 2, "cup"), ("Cinnamon", 0.5, "tsp")],
     ["Simmer oats and milk for 5 minutes.", "Stir in diced apple and cinnamon.", "Cook 3 more minutes and serve warm."]),
    ("Turkey Chili", "Dinner", "One-pot chili that is even better the next day.", 15, 50, 6, 0,
     [("Ground turkey", 1, "lb"), ("Kidney beans", 2, "can"), ("Diced tomatoes", 1, "can"), ("Chili powder", 2, "tbsp")],
     ["Brown the turkey in a large pot.", "Add beans, tomatoes and chili powder.", "Simmer 45 minutes, stirring occasionally."]),
    ("Grilled Cheese and Tomato Soup", "Lunch", "The classic pairing.", 5, 20, 2, 0,
     [("Bread", 4, "slice"), ("Cheddar", 4, "slice"), ("Tomato soup", 1, "can"), ("Butter", 2, "tbsp")],
     ["Heat the soup in a small pot.", "Butter the bread and layer cheese between slices.",
      "Toast in a pan until golden and melted."]),
    ("Baked Apple Crisp", "Dessert", "Warm apples under a crunchy oat topping.", 15, 35, 6, 1,
     [("Apples", 6, ""), ("Rolled oats", 1, "cup"), ("Brown sugar", 0.5, "cup"), ("Butter", 0.5, "cup")],
     ["Slice apples and layer in a baking dish.", "Mix oats, sugar and butter into crumbs and sprinkle on top.",
      "Bake at 350F for 35 minutes."]),
    ("Sheet Pan Sausage and Veggies", "Dinner", "Easy weeknight dinner with one pan to wash.", 10, 30, 4, 0,
     [("Sausage", 1, "lb"), ("Potatoes", 3, ""), ("Brussels sprouts", 2, "cup"), ("Olive oil", 2, "tbsp")],
     ["Chop everything into bite-sized pieces.", "Toss with olive oil, salt and pepper on a sheet pan.",
      "Roast at 425F for 30 minutes."]),
]


def seed_db(db):
    db.execute("INSERT INTO users (id, username) VALUES (?, 'guest')", (DEFAULT_USER_ID,))
    recipe_ids = []
    for title, cat, desc, prep, cook, serv, fav, ingredients, steps in SAMPLE_RECIPES:
        cur = db.execute(
            "INSERT INTO recipes (user_id, title, category, description, prep_minutes,"
            " cook_minutes, servings, is_favorite) VALUES (?,?,?,?,?,?,?,?)",
            (DEFAULT_USER_ID, title, cat, desc, prep, cook, serv, fav))
        rid = cur.lastrowid
        recipe_ids.append(rid)
        for name, qty, unit in ingredients:
            db.execute("INSERT INTO ingredients (recipe_id, name, quantity, unit) VALUES (?,?,?,?)",
                       (rid, name, qty, unit))
        for pos, text in enumerate(steps, start=1):
            db.execute("INSERT INTO steps (recipe_id, position, instruction) VALUES (?,?,?)",
                       (rid, pos, text))

    # Plan dinners for the current week so "Tonight" always has something to show.
    dinners = [rid for rid, r in zip(recipe_ids, SAMPLE_RECIPES) if r[1] == "Dinner"]
    monday = date.today() - timedelta(days=date.today().weekday())
    for i in range(7):
        day = (monday + timedelta(days=i)).isoformat()
        db.execute("INSERT INTO meal_plan (user_id, recipe_id, plan_date, meal_slot) VALUES (?,?,?,'dinner')",
                   (DEFAULT_USER_ID, dinners[i % len(dinners)], day))
