"""Order creation, stock holding and payment state changes."""
from db import get_db

MAX_QTY = 10
DELIVERY = 8000        # paise
FREE_ABOVE = 200000    # paise
HOLD_MINUTES = 30


class OutOfStock(Exception):
    pass


def delivery_for(subtotal):
    return 0 if subtotal >= FREE_ABOVE else DELIVERY


def cart_lines(cart):
    """cart is {"productid:size": qty}. Prices always come from the database."""
    db, lines = get_db(), []
    for key, qty in cart.items():
        pid, _, size = key.partition(":")
        p = db.execute("SELECT * FROM products WHERE id=? AND active=1", (pid,)).fetchone()
        if p:
            lines.append({"key": key, "product": p, "size": size, "qty": qty,
                          "amount": p["price"] * qty})
    return lines


def _take(db, product_id, qty):
    cur = db.execute("UPDATE products SET stock=stock-? WHERE id=? AND stock>=?",
                     (qty, product_id, qty))
    return cur.rowcount == 1


def place(user_id, lines, address, method):
    db = get_db()
    subtotal = sum(l["amount"] for l in lines)
    delivery = delivery_for(subtotal)
    db.execute("BEGIN IMMEDIATE")
    try:
        for l in lines:
            if not _take(db, l["product"]["id"], l["qty"]):
                raise OutOfStock(l["product"]["name"])
        oid = db.execute(
            "INSERT INTO orders(user_id,name,phone,address,city,pin,method,status,delivery,total)"
            " VALUES(?,?,?,?,?,?,?,?,?,?)",
            (user_id, address["name"], address["phone"], address["address"], address["city"],
             address["pin"], method, "placed" if method == "cod" else "pending_payment",
             delivery, subtotal + delivery)).lastrowid
        db.executemany(
            "INSERT INTO order_items(order_id,product_id,name,size,price,qty) VALUES(?,?,?,?,?,?)",
            [(oid, l["product"]["id"], l["product"]["name"], l["size"], l["product"]["price"],
              l["qty"]) for l in lines])
        db.execute("COMMIT")
        return oid
    except Exception:
        db.execute("ROLLBACK")
        raise


def cancel(order_id, note="", only_if_pending=False):
    """Cancel once, returning held stock."""
    db = get_db()
    db.execute("BEGIN IMMEDIATE")
    o = db.execute("SELECT * FROM orders WHERE id=?", (order_id,)).fetchone()
    if not o or o["status"] == "cancelled" or (only_if_pending and o["status"] != "pending_payment"):
        db.execute("ROLLBACK")
        return
    if o["stock_held"]:
        for i in db.execute("SELECT * FROM order_items WHERE order_id=?", (order_id,)).fetchall():
            db.execute("UPDATE products SET stock=stock+? WHERE id=?", (i["qty"], i["product_id"]))
    if o["paid"]:
        note = "Paid order cancelled: refund it from the Razorpay Dashboard."
    db.execute("UPDATE orders SET status='cancelled', stock_held=0, note=? WHERE id=?",
               (note, order_id))
    db.execute("COMMIT")


def release_expired():
    rows = get_db().execute(
        "SELECT id FROM orders WHERE status='pending_payment' AND created < datetime('now', ?)",
        (f"-{HOLD_MINUTES} minutes",)).fetchall()
    for r in rows:
        cancel(r["id"], "Payment not received in time.", only_if_pending=True)


def mark_paid(order_id, payment_id):
    """Safe to call twice (browser callback and webhook both call it)."""
    db = get_db()
    db.execute("BEGIN IMMEDIATE")
    o = db.execute("SELECT * FROM orders WHERE id=?", (order_id,)).fetchone()
    if o["paid"]:
        db.execute("ROLLBACK")
        return
    status, held, note = "placed", o["stock_held"], ""
    if o["status"] == "cancelled":
        # Money arrived after the hold ended. Take the stock again if all of it is there.
        items = db.execute(
            "SELECT product_id, SUM(qty) AS qty FROM order_items WHERE order_id=? GROUP BY product_id",
            (order_id,)).fetchall()
        db.execute("SAVEPOINT retake")
        if all(_take(db, i["product_id"], i["qty"]) for i in items):
            held = 1
        else:
            db.execute("ROLLBACK TO retake")
            status, note = "cancelled", "Paid after stock ran out: refund from the Razorpay Dashboard."
        db.execute("RELEASE retake")
    db.execute("UPDATE orders SET paid=1, razorpay_payment_id=?, status=?, stock_held=?, note=?"
               " WHERE id=?", (payment_id, status, held, note, order_id))
    db.execute("COMMIT")
