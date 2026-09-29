DROP TABLE IF EXISTS shopping_items;
DROP TABLE IF EXISTS meal_plan;
DROP TABLE IF EXISTS steps;
DROP TABLE IF EXISTS ingredients;
DROP TABLE IF EXISTS recipes;
DROP TABLE IF EXISTS users;

CREATE TABLE users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    username      TEXT NOT NULL UNIQUE,
    email         TEXT UNIQUE,
    password_hash TEXT
);

CREATE TABLE recipes (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id      INTEGER NOT NULL REFERENCES users(id),
    title        TEXT NOT NULL,
    description  TEXT,
    category     TEXT NOT NULL,            -- Breakfast, Lunch, Dinner, Dessert, Snack
    prep_minutes INTEGER DEFAULT 0,
    cook_minutes INTEGER DEFAULT 0,
    servings     INTEGER DEFAULT 4,
    is_favorite  INTEGER DEFAULT 0,        -- 0 or 1
    deleted_at   TEXT                      -- NULL = active, date = in Trash
);

CREATE TABLE ingredients (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    recipe_id INTEGER NOT NULL REFERENCES recipes(id) ON DELETE CASCADE,
    name      TEXT NOT NULL,
    quantity  REAL,
    unit      TEXT
);

CREATE TABLE steps (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    recipe_id   INTEGER NOT NULL REFERENCES recipes(id) ON DELETE CASCADE,
    position    INTEGER NOT NULL,
    instruction TEXT NOT NULL
);

CREATE TABLE meal_plan (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id   INTEGER NOT NULL REFERENCES users(id),
    recipe_id INTEGER NOT NULL REFERENCES recipes(id),
    plan_date TEXT NOT NULL,               -- YYYY-MM-DD
    meal_slot TEXT NOT NULL                -- breakfast, lunch, dinner
);

CREATE TABLE shopping_items (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id  INTEGER NOT NULL REFERENCES users(id),
    name     TEXT NOT NULL,
    quantity TEXT,
    checked  INTEGER DEFAULT 0
);
