import os
import re
import secrets
import time
import uuid
from functools import wraps
from pathlib import Path

import click
from dotenv import load_dotenv
from flask import (Flask, abort, flash, g, redirect, render_template, request,
                   send_from_directory, session, url_for)
from werkzeug.security import check_password_hash, generate_password_hash

import orders
import payments
from db import close_db, get_db, init_db

BASE = Path(__file__).parent
CATEGORIES = ["Necklaces", "Earrings", "Bangles", "Rings", "Anklets"]


def create_app(overrides=None):
    load_dotenv(BASE / ".env")
    app = Flask(__name__, instance_path=str(BASE / "instance"))
    Path(app.instance_path).mkdir(exist_ok=True)
    secret = os.getenv("SECRET_KEY")
    if not secret:
        key_file = Path(app.instance_path) / "secret_key"
        if not key_file.exists():
            key_file.write_text(secrets.token_hex(32))
        secret = key_file.read_text()
    app.config.update(
        SECRET_KEY=secret,
        DATABASE=str(Path(app.instance_path) / "store.db"),
        UPLOADS=str(Path(app.instance_path) / "uploads"),
        MAX_CONTENT_LENGTH=3 * 1024 * 1024,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=os.getenv("HTTPS") == "1",
        RAZORPAY_KEY_ID=os.getenv("RAZORPAY_KEY_ID", ""),
        RAZORPAY_KEY_SECRET=os.getenv("RAZORPAY_KEY_SECRET", ""),
        RAZORPAY_WEBHOOK_SECRET=os.getenv("RAZORPAY_WEBHOOK_SECRET", ""),
        STORE_NAME=os.getenv("STORE_NAME", "Maalai Jewels"))
    app.config.update(overrides or {})
    Path(app.config["UPLOADS"]).mkdir(parents=True, exist_ok=True)
    app.teardown_appcontext(close_db)
    with app.app_context():
        init_db()
    register(app)
    return app


def login_required(view):
    @wraps(view)
    def wrapped(*a, **kw):
        if not g.user:
            flash("Log in to continue.")
            return redirect(url_for("login", next=request.path))
        return view(*a, **kw)
    return wrapped


def admin_required(view):
    @wraps(view)
    def wrapped(*a, **kw):
        if not g.user or not g.user["is_admin"]:
            abort(403)
        return view(*a, **kw)
    return wrapped


def safe_next(target):
    if target and target.startswith("/") and not target.startswith("//") and "\\" not in target:
        return target
    return url_for("home")


def my_order(oid):
    o = get_db().execute("SELECT * FROM orders WHERE id=?", (oid,)).fetchone()
    if not o or (o["user_id"] != g.user["id"] and not g.user["is_admin"]):
        abort(404)
    return o


def items_of(oid):
    return get_db().execute("SELECT * FROM order_items WHERE order_id=?", (oid,)).fetchall()


def register(app):
    failures = {}  # login throttling, per process

    @app.template_filter("inr")
    def inr(paise):
        return f"₹{paise / 100:,.0f}" if paise % 100 == 0 else f"₹{paise / 100:,.2f}"

    @app.before_request
    def before():
        if request.endpoint == "static":
            return
        uid = session.get("uid")
        g.user = get_db().execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone() if uid else None
        if request.method == "POST" and request.endpoint != "webhook":
            token = request.form.get("csrf", "")
            if not session.get("csrf") or not secrets.compare_digest(token.encode(), session["csrf"].encode()):
                abort(400, "Your session expired. Reload the page and try again.")
        orders.release_expired()

    @app.context_processor
    def inject():
        if "csrf" not in session:
            session["csrf"] = secrets.token_hex(16)
        return {"csrf": session["csrf"], "user": g.get("user"), "store": app.config["STORE_NAME"],
                "cart_count": sum(session.get("cart", {}).values()), "categories": CATEGORIES}

    # ---------- catalogue ----------
    @app.get("/")
    def home():
        a = request.args
        sql, args = "SELECT * FROM products WHERE active=1", []
        if a.get("q"):
            sql += " AND (name || ' ' || description || ' ' || category) LIKE ?"
            args.append(f"%{a['q'].strip()}%")
        for field in ("category", "material"):
            if a.get(field):
                sql += f" AND {field}=?"
                args.append(a[field])
        if a.get("max", "").isdigit():
            sql += " AND price < ?"
            args.append(int(a["max"]) * 100)
        sql += " ORDER BY " + {"lo": "price", "hi": "price DESC", "az": "name"}.get(a.get("sort"), "id")
        db = get_db()
        materials = [r[0] for r in db.execute("SELECT DISTINCT material FROM products WHERE active=1")]
        wished = set()
        if g.user:
            wished = {r[0] for r in db.execute("SELECT product_id FROM wishlist WHERE user_id=?", (g.user["id"],))}
        return render_template("home.html", products=db.execute(sql, args).fetchall(),
                               materials=materials, wished=wished)

    def product_or_404(pid):
        p = get_db().execute("SELECT * FROM products WHERE id=? AND active=1", (pid,)).fetchone()
        return p or abort(404)

    @app.get("/product/<int:pid>")
    def product(pid):
        return render_template("product.html", p=product_or_404(pid))

    @app.get("/image/<name>")
    def image(name):
        return send_from_directory(app.config["UPLOADS"], name)

    @app.get("/info")
    def info():
        return render_template("info.html")

    @app.route("/contact", methods=["GET", "POST"])
    def contact():
        if request.method == "POST":
            f = [request.form.get(k, "").strip()[:1000] for k in ("name", "reach", "message")]
            if all(f):
                get_db().execute("INSERT INTO messages(name,reach,body) VALUES(?,?,?)", f)
                flash("Message sent.")
                return redirect(url_for("contact"))
            flash("Fill in every field.")
        return render_template("contact.html")

    # ---------- accounts ----------
    @app.route("/register", methods=["GET", "POST"], endpoint="register")
    def register_user():
        if request.method == "POST":
            name = request.form.get("name", "").strip()
            email = request.form.get("email", "").strip().lower()
            pw = request.form.get("password", "")
            if not name or not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email) or len(pw) < 8:
                flash("Enter your name, a valid email and a password of at least 8 characters.")
            elif get_db().execute("SELECT 1 FROM users WHERE email=?", (email,)).fetchone():
                flash("That email already has an account. Log in instead.")
            else:
                uid = get_db().execute("INSERT INTO users(name,email,password) VALUES(?,?,?)",
                                       (name, email, generate_password_hash(pw))).lastrowid
                return sign_in(uid)
        return render_template("auth.html", mode="register")

    def sign_in(uid):
        cart = session.get("cart", {})
        session.clear()
        session["uid"], session["cart"] = uid, cart
        return redirect(safe_next(request.args.get("next")))

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if request.method == "POST":
            email = request.form.get("email", "").strip().lower()
            key = (request.remote_addr, email)
            recent = [t for t in failures.get(key, []) if t > time.time() - 600]
            if len(recent) >= 5:
                flash("Too many attempts. Try again in 10 minutes.")
            else:
                u = get_db().execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
                if u and check_password_hash(u["password"], request.form.get("password", "")):
                    failures.pop(key, None)
                    return sign_in(u["id"])
                failures[key] = recent + [time.time()]
                flash("Email or password is wrong.")
        return render_template("auth.html", mode="login")

    @app.post("/logout")
    def logout():
        session.clear()
        return redirect(url_for("home"))

    # ---------- bag and wishlist ----------
    @app.post("/cart/add/<int:pid>")
    def cart_add(pid):
        p = product_or_404(pid)
        size = request.form.get("size", "")
        if p["sizes"] and size not in p["sizes"].split(","):
            flash("Select a size to add this piece.")
            return redirect(url_for("product", pid=pid))
        size = size if p["sizes"] else ""
        cart = session.get("cart", {})
        key = f"{pid}:{size}"
        qty = min(cart.get(key, 0) + 1, orders.MAX_QTY, p["stock"])
        if qty < 1:
            flash("This piece is sold out.")
            return redirect(url_for("product", pid=pid))
        cart[key] = qty
        session["cart"] = cart
        flash(f"{p['name']} is in your bag.")
        return redirect(url_for("cart"))

    @app.post("/cart/update")
    def cart_update():
        cart = session.get("cart", {})
        key = request.form.get("key", "")
        qty = request.form.get("qty", type=int)
        if key in cart and qty is not None:
            if qty < 1:
                del cart[key]
            else:
                cart[key] = min(qty, orders.MAX_QTY)
            session["cart"] = cart
        return redirect(url_for("cart"))

    @app.get("/cart")
    def cart():
        lines = orders.cart_lines(session.get("cart", {}))
        sub = sum(l["amount"] for l in lines)
        return render_template("cart.html", lines=lines, subtotal=sub, delivery=orders.delivery_for(sub))

    @app.post("/wishlist/<int:pid>")
    @login_required
    def wishlist_toggle(pid):
        product_or_404(pid)
        db, key = get_db(), (g.user["id"], pid)
        if db.execute("DELETE FROM wishlist WHERE user_id=? AND product_id=?", key).rowcount == 0:
            db.execute("INSERT INTO wishlist VALUES(?,?)", key)
        return redirect(safe_next(request.form.get("back")))

    # The wishlist POST path is not a page, so send people home after logging in from it.
    @app.get("/wishlist/<int:pid>")
    def wishlist_item(pid):
        return redirect(url_for("product", pid=pid))

    @app.get("/wishlist")
    @login_required
    def wishlist():
        rows = get_db().execute(
            "SELECT p.* FROM products p JOIN wishlist w ON w.product_id=p.id "
            "WHERE w.user_id=? AND p.active=1", (g.user["id"],)).fetchall()
        return render_template("wishlist.html", products=rows)

    # ---------- checkout and payment ----------
    @app.route("/checkout", methods=["GET", "POST"])
    @login_required
    def checkout():
        lines = orders.cart_lines(session.get("cart", {}))
        if not lines:
            return redirect(url_for("cart"))
        sub = sum(l["amount"] for l in lines)
        online = payments.configured()
        if request.method == "POST":
            f = {k: request.form.get(k, "").strip()[:300] for k in ("name", "phone", "address", "city", "pin")}
            method = request.form.get("method")
            if not all(f.values()) or not re.fullmatch(r"[6-9]\d{9}", f["phone"]) \
                    or not re.fullmatch(r"[1-9]\d{5}", f["pin"]):
                flash("Check your details: 10-digit mobile number, 6-digit PIN code, and no empty fields.")
            elif method not in ("cod", "razorpay") or (method == "razorpay" and not online):
                flash("Choose an available payment method.")
            else:
                try:
                    oid = orders.place(g.user["id"], lines, f, method)
                except orders.OutOfStock as e:
                    flash(f"Not enough stock for {e}. Reduce the quantity.")
                    return redirect(url_for("cart"))
                if method == "razorpay":
                    total = get_db().execute("SELECT total FROM orders WHERE id=?", (oid,)).fetchone()[0]
                    try:
                        rid = payments.create_order(total, f"order-{oid}")
                    except payments.PaymentError:
                        orders.cancel(oid, "Payment could not be started.")
                        flash("Online payment could not be started. You have not been charged. Try again.")
                        return redirect(url_for("checkout"))
                    get_db().execute("UPDATE orders SET razorpay_order_id=? WHERE id=?", (rid, oid))
                    session["cart"] = {}
                    return redirect(url_for("pay", oid=oid))
                session["cart"] = {}
                return redirect(url_for("order", oid=oid))
        return render_template("checkout.html", subtotal=sub, delivery=orders.delivery_for(sub), online=online)

    @app.get("/order/<int:oid>/pay")
    @login_required
    def pay(oid):
        o = my_order(oid)
        if o["status"] != "pending_payment" or not payments.configured():
            return redirect(url_for("order", oid=oid))
        options = {"key": app.config["RAZORPAY_KEY_ID"], "amount": o["total"], "currency": "INR",
                   "name": app.config["STORE_NAME"], "description": f"Order #{oid}",
                   "order_id": o["razorpay_order_id"], "theme": {"color": "#0f3d3e"},
                   "prefill": {"name": o["name"], "contact": "+91" + o["phone"], "email": g.user["email"]}}
        return render_template("pay.html", o=o, options=options)

    @app.post("/order/<int:oid>/verify")
    @login_required
    def verify(oid):
        o = my_order(oid)
        pid = request.form.get("razorpay_payment_id", "")
        sig = request.form.get("razorpay_signature", "")
        # The Razorpay order id comes from our database, never from the browser.
        if o["razorpay_order_id"] and payments.valid_payment(o["razorpay_order_id"], pid, sig):
            orders.mark_paid(oid, pid)
            flash("Payment received.")
        else:
            flash("We could not verify that payment. If money was debited, contact us with your order number.")
        return redirect(url_for("order", oid=oid))

    @app.post("/webhook/razorpay")
    def webhook():
        if not payments.valid_webhook(request.get_data(), request.headers.get("X-Razorpay-Signature", "")):
            abort(400)
        event = request.get_json(silent=True) or {}
        if event.get("event") in ("payment.captured", "order.paid"):
            pay_ = event.get("payload", {}).get("payment", {}).get("entity", {})
            o = get_db().execute("SELECT * FROM orders WHERE razorpay_order_id=?",
                                 (pay_.get("order_id"),)).fetchone()
            if o and pay_.get("amount") == o["total"] and pay_.get("currency") == "INR":
                orders.mark_paid(o["id"], pay_.get("id"))
        return {"ok": True}

    @app.get("/orders")
    @login_required
    def my_orders():
        rows = get_db().execute("SELECT * FROM orders WHERE user_id=? ORDER BY id DESC", (g.user["id"],)).fetchall()
        return render_template("orders.html", orders=rows)

    @app.get("/order/<int:oid>")
    @login_required
    def order(oid):
        return render_template("order.html", o=my_order(oid), items=items_of(oid))

    # ---------- admin ----------
    @app.get("/admin")
    @admin_required
    def admin():
        db = get_db()
        rows = db.execute("SELECT * FROM orders ORDER BY id DESC LIMIT 200").fetchall()
        return render_template(
            "admin/dashboard.html", orders=rows,
            items={o["id"]: items_of(o["id"]) for o in rows},
            products=db.execute("SELECT * FROM products ORDER BY id").fetchall(),
            messages=db.execute("SELECT * FROM messages ORDER BY id DESC LIMIT 50").fetchall(),
            revenue=db.execute("SELECT COALESCE(SUM(total),0) FROM orders WHERE status!='cancelled' "
                               "AND (paid=1 OR (method='cod' AND status='delivered'))").fetchone()[0])

    @app.post("/admin/order/<int:oid>")
    @admin_required
    def admin_order(oid):
        o = my_order(oid)
        new = request.form.get("status")
        allowed = {"placed": ("shipped", "cancelled"), "shipped": ("delivered", "cancelled"),
                   "pending_payment": ("cancelled",)}
        if new not in allowed.get(o["status"], ()):
            flash("That status change is not allowed.")
        elif new == "cancelled":
            orders.cancel(oid, "Cancelled by the store.")
        else:
            get_db().execute("UPDATE orders SET status=? WHERE id=?", (new, oid))
        return redirect(url_for("admin"))

    @app.route("/admin/product/new", methods=["GET", "POST"], defaults={"pid": None})
    @app.route("/admin/product/<int:pid>", methods=["GET", "POST"])
    @admin_required
    def admin_product(pid):
        db = get_db()
        p = db.execute("SELECT * FROM products WHERE id=?", (pid,)).fetchone() if pid else None
        if pid and not p:
            abort(404)
        if request.method == "POST":
            f = request.form
            try:
                price, stock = round(float(f["price"]) * 100), int(f["stock"])
                if not f["name"].strip() or f["category"] not in CATEGORIES or price < 100 or stock < 0:
                    raise ValueError
                img = save_image(request.files.get("image")) or (p["image"] if p else None)
            except (ValueError, OverflowError, KeyError):
                flash("Check the fields. Price is at least ₹1, stock is 0 or more, photo is JPG, PNG or WebP.")
            else:
                sizes = ",".join(s.strip() for s in f.get("sizes", "").split(",") if s.strip())
                values = (f["name"].strip(), f["category"], f.get("material", "").strip(), price, stock,
                          sizes, f.get("description", "").strip(), img, 1 if f.get("active") else 0)
                if p:
                    db.execute("UPDATE products SET name=?,category=?,material=?,price=?,stock=?,sizes=?,"
                               "description=?,image=?,active=? WHERE id=?", values + (pid,))
                else:
                    db.execute("INSERT INTO products(name,category,material,price,stock,sizes,description,"
                               "image,active) VALUES(?,?,?,?,?,?,?,?,?)", values)
                flash("Product saved.")
                return redirect(url_for("admin"))
        return render_template("admin/product.html", p=p)

    def save_image(file):
        if not file or not file.filename:
            return None
        head = file.stream.read(12)
        file.stream.seek(0)
        if head.startswith(b"\xff\xd8\xff"):
            ext = "jpg"
        elif head.startswith(b"\x89PNG\r\n\x1a\n"):
            ext = "png"
        elif head[:4] == b"RIFF" and head[8:] == b"WEBP":
            ext = "webp"
        else:
            raise ValueError("not an image")
        name = f"{uuid.uuid4().hex}.{ext}"
        file.save(Path(app.config["UPLOADS"]) / name)
        return name

    @app.cli.command("create-admin")
    @click.option("--email", prompt=True)
    @click.option("--password", prompt=True, hide_input=True, confirmation_prompt=True)
    def create_admin(email, password):
        if len(password) < 8:
            raise click.ClickException("Use at least 8 characters.")
        get_db().execute(
            "INSERT INTO users(name,email,password,is_admin) VALUES('Admin',?,?,1) "
            "ON CONFLICT(email) DO UPDATE SET password=excluded.password, is_admin=1",
            (email.strip().lower(), generate_password_hash(password)))
        click.echo("Admin account ready.")


if __name__ == "__main__":
    create_app().run(debug=os.getenv("FLASK_DEBUG") == "1")
