import os
import sqlite3

from flask import current_app, g

SCHEMA = """
CREATE TABLE IF NOT EXISTS restaurants (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    address TEXT,
    phone TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS menu_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    restaurant_id INTEGER NOT NULL REFERENCES restaurants(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    category TEXT,
    price REAL NOT NULL CHECK (price >= 0),
    available INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS customers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    email TEXT UNIQUE,
    phone TEXT
);
CREATE TABLE IF NOT EXISTS orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    customer_id INTEGER NOT NULL REFERENCES customers(id),
    restaurant_id INTEGER NOT NULL REFERENCES restaurants(id),
    status TEXT NOT NULL DEFAULT 'PLACED',
    total REAL NOT NULL DEFAULT 0,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS order_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id INTEGER NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
    menu_item_id INTEGER NOT NULL REFERENCES menu_items(id),
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    unit_price REAL NOT NULL
);
"""


def _connect(path):
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def get_db():
    if "db" not in g:
        g.db = _connect(current_app.config["DB_PATH"])
    return g.db


def close_db(_exc=None):
    conn = g.pop("db", None)
    if conn is not None:
        conn.close()


def init_db(path):
    folder = os.path.dirname(os.path.abspath(path))
    os.makedirs(folder, exist_ok=True)
    conn = _connect(path)
    conn.executescript(SCHEMA)
    conn.commit()
    conn.close()


def seed_demo(path):
    """Insert a little demo data, only when the database is empty."""
    conn = _connect(path)
    if conn.execute("SELECT COUNT(*) FROM restaurants").fetchone()[0] == 0:
        conn.execute(
            "INSERT INTO restaurants (name, address, phone) VALUES (?, ?, ?)",
            ("Spice Garden", "12 MG Road, Mumbai", "022-5550101"),
        )
        items = [
            (1, "Paneer Tikka", "Starter", 220.0, 1),
            (1, "Veg Biryani", "Main", 260.0, 1),
            (1, "Masala Chai", "Beverage", 40.0, 1),
        ]
        conn.executemany(
            "INSERT INTO menu_items (restaurant_id, name, category, price, available) "
            "VALUES (?, ?, ?, ?, ?)",
            items,
        )
        conn.execute(
            "INSERT INTO customers (name, email, phone) VALUES (?, ?, ?)",
            ("Demo Customer", "demo@example.com", "9999999999"),
        )
        conn.commit()
    conn.close()
