import sqlite3

from flask import Blueprint, jsonify, request

from . import metrics
from .db import get_db

bp = Blueprint("api", __name__, url_prefix="/api")

ORDER_STATUSES = ("PLACED", "PREPARING", "SERVED", "CANCELLED")

# (column, type, required)
SPECS = {
    "restaurants": [("name", "str", True), ("address", "str", False), ("phone", "str", False)],
    "menu_items": [
        ("restaurant_id", "int", True),
        ("name", "str", True),
        ("category", "str", False),
        ("price", "num", True),
        ("available", "bool", False),
    ],
    "customers": [("name", "str", True), ("email", "str", False), ("phone", "str", False)],
}
FILTERS = {
    "restaurants": [],
    "menu_items": ["restaurant_id", "category"],
    "customers": [],
}


class ValidationError(Exception):
    pass


@bp.errorhandler(ValidationError)
def _validation_error(exc):
    return jsonify(error=str(exc)), 400


@bp.errorhandler(404)
def _not_found(_exc):
    return jsonify(error="not found"), 404


@bp.errorhandler(405)
def _not_allowed(_exc):
    return jsonify(error="method not allowed"), 405


def json_body():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise ValidationError("request body must be a JSON object")
    return data


def parse_fields(spec, data, partial=False):
    values = {}
    for name, kind, required in spec:
        if name not in data:
            if required and not partial:
                raise ValidationError("%s is required" % name)
            continue
        value = data[name]
        if kind == "str":
            if value is None or value == "":
                if required:
                    raise ValidationError("%s must not be empty" % name)
                values[name] = None
                continue
            if not isinstance(value, str):
                raise ValidationError("%s must be a string" % name)
            value = value.strip()
            if required and not value:
                raise ValidationError("%s must not be empty" % name)
            if len(value) > 200:
                raise ValidationError("%s is too long" % name)
            values[name] = value or None
        elif kind == "int":
            if isinstance(value, bool) or not isinstance(value, int):
                raise ValidationError("%s must be an integer" % name)
            values[name] = value
        elif kind == "num":
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValidationError("%s must be a number" % name)
            if value < 0:
                raise ValidationError("%s must be >= 0" % name)
            values[name] = float(value)
        elif kind == "bool":
            if not isinstance(value, bool):
                raise ValidationError("%s must be true or false" % name)
            values[name] = 1 if value else 0
    return values


def row_out(table, row):
    out = dict(row)
    for name, kind, _ in SPECS[table]:
        if kind == "bool" and name in out:
            out[name] = bool(out[name])
    return out


def make_crud(table, path):
    spec = SPECS[table]
    # The table name comes from the fixed SPECS dict above, never from user input,
    # so building these SQL strings is safe (hence the nosec markers for Bandit).
    select_all = "SELECT * FROM %s" % table  # nosec B608
    select_one = "SELECT * FROM %s WHERE id = ?" % table  # nosec B608
    exists_one = "SELECT 1 FROM %s WHERE id = ?" % table  # nosec B608
    delete_one = "DELETE FROM %s WHERE id = ?" % table  # nosec B608

    def list_items():
        db = get_db()
        sql, params = select_all, []
        clauses = []
        for col in FILTERS[table]:
            if request.args.get(col) is not None:
                clauses.append("%s = ?" % col)
                params.append(request.args[col])
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY id"
        return jsonify([row_out(table, r) for r in db.execute(sql, params).fetchall()])

    def create_item():
        values = parse_fields(spec, json_body())
        db = get_db()
        cols = list(values)
        marks = ", ".join("?" for _ in cols)
        insert_sql = "INSERT INTO %s (%s) VALUES (%s)" % (table, ", ".join(cols), marks)  # nosec B608
        try:
            cur = db.execute(insert_sql, [values[c] for c in cols])
            db.commit()
        except sqlite3.IntegrityError as exc:
            return integrity_response(exc)
        row = db.execute(select_one, (cur.lastrowid,)).fetchone()
        return jsonify(row_out(table, row)), 201

    def get_item(item_id):
        row = get_db().execute(select_one, (item_id,)).fetchone()
        if row is None:
            return jsonify(error="not found"), 404
        return jsonify(row_out(table, row))

    def update_item(item_id):
        values = parse_fields(spec, json_body(), partial=True)
        if not values:
            raise ValidationError("no valid fields to update")
        db = get_db()
        if db.execute(exists_one, (item_id,)).fetchone() is None:
            return jsonify(error="not found"), 404
        cols = list(values)
        set_clause = ", ".join("%s = ?" % c for c in cols)
        update_sql = "UPDATE %s SET %s WHERE id = ?" % (table, set_clause)  # nosec B608
        try:
            db.execute(update_sql, [values[c] for c in cols] + [item_id])
            db.commit()
        except sqlite3.IntegrityError as exc:
            return integrity_response(exc)
        row = db.execute(select_one, (item_id,)).fetchone()
        return jsonify(row_out(table, row))

    def delete_item(item_id):
        db = get_db()
        if db.execute(exists_one, (item_id,)).fetchone() is None:
            return jsonify(error="not found"), 404
        try:
            db.execute(delete_one, (item_id,))
            db.commit()
        except sqlite3.IntegrityError:
            return jsonify(error="cannot delete: record is referenced by orders"), 409
        return "", 204

    bp.add_url_rule(path, "list_" + table, list_items, methods=["GET"])
    bp.add_url_rule(path, "create_" + table, create_item, methods=["POST"])
    bp.add_url_rule(path + "/<int:item_id>", "get_" + table, get_item, methods=["GET"])
    bp.add_url_rule(path + "/<int:item_id>", "update_" + table, update_item, methods=["PUT", "PATCH"])
    bp.add_url_rule(path + "/<int:item_id>", "delete_" + table, delete_item, methods=["DELETE"])


def integrity_response(exc):
    msg = str(exc)
    if "UNIQUE" in msg:
        return jsonify(error="duplicate value (already exists)"), 409
    if "FOREIGN KEY" in msg:
        return jsonify(error="referenced record does not exist"), 400
    return jsonify(error="invalid data"), 400


make_crud("restaurants", "/restaurants")
make_crud("menu_items", "/menu-items")
make_crud("customers", "/customers")


# ---------------------------------------------------------------- orders
def load_order(db, order_id):
    order = db.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()
    if order is None:
        return None
    out = dict(order)
    items = db.execute(
        "SELECT oi.menu_item_id, m.name, oi.quantity, oi.unit_price "
        "FROM order_items oi JOIN menu_items m ON m.id = oi.menu_item_id "
        "WHERE oi.order_id = ? ORDER BY oi.id",
        (order_id,),
    ).fetchall()
    out["items"] = [dict(i) for i in items]
    return out


@bp.get("/orders")
def list_orders():
    db = get_db()
    sql, params, clauses = "SELECT id FROM orders", [], []
    for col in ("status", "customer_id", "restaurant_id"):
        if request.args.get(col) is not None:
            clauses.append("%s = ?" % col)
            params.append(request.args[col])
    if clauses:
        sql += " WHERE " + " AND ".join(clauses)
    sql += " ORDER BY id"
    ids = [r["id"] for r in db.execute(sql, params).fetchall()]
    return jsonify([load_order(db, i) for i in ids])


@bp.post("/orders")
def create_order():
    data = json_body()
    for key in ("customer_id", "restaurant_id"):
        v = data.get(key)
        if isinstance(v, bool) or not isinstance(v, int):
            raise ValidationError("%s must be an integer" % key)
    items = data.get("items")
    if not isinstance(items, list) or not items:
        raise ValidationError("items must be a non-empty list")

    db = get_db()
    if db.execute("SELECT 1 FROM customers WHERE id = ?", (data["customer_id"],)).fetchone() is None:
        raise ValidationError("customer does not exist")
    if db.execute("SELECT 1 FROM restaurants WHERE id = ?", (data["restaurant_id"],)).fetchone() is None:
        raise ValidationError("restaurant does not exist")

    lines, total = [], 0.0
    for entry in items:
        if not isinstance(entry, dict):
            raise ValidationError("each item must be an object")
        mid, qty = entry.get("menu_item_id"), entry.get("quantity", 1)
        if isinstance(mid, bool) or not isinstance(mid, int):
            raise ValidationError("menu_item_id must be an integer")
        if isinstance(qty, bool) or not isinstance(qty, int) or not 1 <= qty <= 100:
            raise ValidationError("quantity must be an integer between 1 and 100")
        menu = db.execute(
            "SELECT * FROM menu_items WHERE id = ? AND restaurant_id = ?",
            (mid, data["restaurant_id"]),
        ).fetchone()
        if menu is None:
            raise ValidationError("menu item %s not found for this restaurant" % mid)
        if not menu["available"]:
            raise ValidationError("menu item %s is not available" % mid)
        lines.append((mid, qty, menu["price"]))
        total += menu["price"] * qty

    cur = db.execute(
        "INSERT INTO orders (customer_id, restaurant_id, status, total) VALUES (?, ?, 'PLACED', ?)",
        (data["customer_id"], data["restaurant_id"], round(total, 2)),
    )
    order_id = cur.lastrowid
    db.executemany(
        "INSERT INTO order_items (order_id, menu_item_id, quantity, unit_price) VALUES (?, ?, ?, ?)",
        [(order_id, mid, qty, price) for mid, qty, price in lines],
    )
    db.commit()
    metrics.order_created()
    return jsonify(load_order(db, order_id)), 201


@bp.get("/orders/<int:order_id>")
def get_order(order_id):
    order = load_order(get_db(), order_id)
    if order is None:
        return jsonify(error="not found"), 404
    return jsonify(order)


@bp.patch("/orders/<int:order_id>/status")
def update_order_status(order_id):
    status = json_body().get("status")
    if status not in ORDER_STATUSES:
        raise ValidationError("status must be one of: " + ", ".join(ORDER_STATUSES))
    db = get_db()
    if db.execute("SELECT 1 FROM orders WHERE id = ?", (order_id,)).fetchone() is None:
        return jsonify(error="not found"), 404
    db.execute("UPDATE orders SET status = ? WHERE id = ?", (status, order_id))
    db.commit()
    return jsonify(load_order(db, order_id))


@bp.delete("/orders/<int:order_id>")
def delete_order(order_id):
    db = get_db()
    if db.execute("SELECT 1 FROM orders WHERE id = ?", (order_id,)).fetchone() is None:
        return jsonify(error="not found"), 404
    db.execute("DELETE FROM orders WHERE id = ?", (order_id,))
    db.commit()
    return "", 204


@bp.get("/stats")
def stats():
    db = get_db()
    one = lambda sql: db.execute(sql).fetchone()[0]  # noqa: E731
    return jsonify(
        restaurants=one("SELECT COUNT(*) FROM restaurants"),
        menu_items=one("SELECT COUNT(*) FROM menu_items"),
        customers=one("SELECT COUNT(*) FROM customers"),
        orders=one("SELECT COUNT(*) FROM orders"),
        revenue=round(one("SELECT COALESCE(SUM(total), 0) FROM orders WHERE status != 'CANCELLED'"), 2),
    )
