"""
Робота з базою даних (SQLite).
Тут зберігаються товари, вміст кошиків клієнтів та замовлення.
SQLite обрано тому, що для невеликого/середнього магазину цього
достатньо і не потрібен окремий сервер бази даних.
"""
import sqlite3
import json
from datetime import datetime
from contextlib import contextmanager

from config import DB_PATH


@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    """Створює таблиці, якщо їх ще немає. Викликається один раз при старті бота."""
    with get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS categories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS products (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                category_id INTEGER,
                name TEXT NOT NULL,
                description TEXT DEFAULT '',
                price REAL NOT NULL,
                photo_file_id TEXT,
                in_stock INTEGER DEFAULT 1,
                created_at TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (category_id) REFERENCES categories(id)
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS cart_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                product_id INTEGER NOT NULL,
                qty INTEGER NOT NULL DEFAULT 1,
                UNIQUE(user_id, product_id),
                FOREIGN KEY (product_id) REFERENCES products(id)
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                username TEXT,
                full_name TEXT,
                phone TEXT,
                delivery_method TEXT,
                delivery_address TEXT,
                items_json TEXT NOT NULL,
                total REAL NOT NULL,
                status TEXT DEFAULT 'waiting_payment',
                payment_proof_file_id TEXT,
                created_at TEXT DEFAULT (datetime('now'))
            )
        """)


# ---------- КАТЕГОРІЇ ----------

def add_category(name: str) -> int:
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT OR IGNORE INTO categories (name) VALUES (?)", (name,)
        )
        row = conn.execute(
            "SELECT id FROM categories WHERE name = ?", (name,)
        ).fetchone()
        return row["id"]


def get_categories():
    with get_conn() as conn:
        return conn.execute("SELECT * FROM categories ORDER BY name").fetchall()


# ---------- ТОВАРИ ----------

def add_product(name, description, price, category_id=None, photo_file_id=None):
    with get_conn() as conn:
        cur = conn.execute(
            """INSERT INTO products (name, description, price, category_id, photo_file_id)
               VALUES (?, ?, ?, ?, ?)""",
            (name, description, price, category_id, photo_file_id),
        )
        return cur.lastrowid


def get_products_by_category(category_id):
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM products WHERE category_id = ? AND in_stock = 1 ORDER BY id DESC",
            (category_id,),
        ).fetchall()


def get_all_products(only_in_stock=True):
    with get_conn() as conn:
        q = "SELECT * FROM products"
        if only_in_stock:
            q += " WHERE in_stock = 1"
        q += " ORDER BY id DESC"
        return conn.execute(q).fetchall()


def get_product(product_id):
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM products WHERE id = ?", (product_id,)
        ).fetchone()


def delete_product(product_id):
    with get_conn() as conn:
        conn.execute("UPDATE products SET in_stock = 0 WHERE id = ?", (product_id,))


def set_product_stock(product_id, in_stock: bool):
    with get_conn() as conn:
        conn.execute(
            "UPDATE products SET in_stock = ? WHERE id = ?",
            (1 if in_stock else 0, product_id),
        )


# ---------- КОШИК ----------

def add_to_cart(user_id, product_id, qty=1):
    with get_conn() as conn:
        existing = conn.execute(
            "SELECT * FROM cart_items WHERE user_id = ? AND product_id = ?",
            (user_id, product_id),
        ).fetchone()
        if existing:
            conn.execute(
                "UPDATE cart_items SET qty = qty + ? WHERE id = ?",
                (qty, existing["id"]),
            )
        else:
            conn.execute(
                "INSERT INTO cart_items (user_id, product_id, qty) VALUES (?, ?, ?)",
                (user_id, product_id, qty),
            )


def update_cart_qty(user_id, product_id, qty):
    with get_conn() as conn:
        if qty <= 0:
            conn.execute(
                "DELETE FROM cart_items WHERE user_id = ? AND product_id = ?",
                (user_id, product_id),
            )
        else:
            conn.execute(
                "UPDATE cart_items SET qty = ? WHERE user_id = ? AND product_id = ?",
                (qty, user_id, product_id),
            )


def remove_from_cart(user_id, product_id):
    with get_conn() as conn:
        conn.execute(
            "DELETE FROM cart_items WHERE user_id = ? AND product_id = ?",
            (user_id, product_id),
        )


def get_cart(user_id):
    """Повертає список товарів у кошику з деталями товару та підсумковою сумою."""
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT ci.qty, p.* FROM cart_items ci
               JOIN products p ON p.id = ci.product_id
               WHERE ci.user_id = ?""",
            (user_id,),
        ).fetchall()
        total = sum(r["price"] * r["qty"] for r in rows)
        return rows, total


def clear_cart(user_id):
    with get_conn() as conn:
        conn.execute("DELETE FROM cart_items WHERE user_id = ?", (user_id,))


# ---------- ЗАМОВЛЕННЯ ----------

def create_order(user_id, username, full_name, phone, delivery_method,
                  delivery_address, items, total):
    """items - список словників [{'name':..., 'price':..., 'qty':...}, ...]"""
    with get_conn() as conn:
        cur = conn.execute(
            """INSERT INTO orders
               (user_id, username, full_name, phone, delivery_method,
                delivery_address, items_json, total, status)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'waiting_payment')""",
            (user_id, username, full_name, phone, delivery_method,
             delivery_address, json.dumps(items, ensure_ascii=False), total),
        )
        return cur.lastrowid


def attach_payment_proof(order_id, file_id):
    with get_conn() as conn:
        conn.execute(
            "UPDATE orders SET payment_proof_file_id = ?, status = 'pending_review' WHERE id = ?",
            (file_id, order_id),
        )


def set_order_status(order_id, status):
    with get_conn() as conn:
        conn.execute("UPDATE orders SET status = ? WHERE id = ?", (status, order_id))


def get_order(order_id):
    with get_conn() as conn:
        return conn.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()


def get_user_orders(user_id):
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM orders WHERE user_id = ? ORDER BY id DESC", (user_id,)
        ).fetchall()


def get_orders_by_status(status):
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM orders WHERE status = ? ORDER BY id DESC", (status,)
        ).fetchall()
