import hashlib
import hmac
import json
import re
import sys
from pathlib import Path

import pytest
import requests

sys.path.insert(0, str(Path(__file__).parent.parent))
import payments  # noqa: E402
from app import create_app  # noqa: E402
from db import get_db  # noqa: E402

ADDRESS = dict(name="A", phone="9000000000", address="1 Street", city="Chennai", pin="600001")


def sign(secret, msg):
    return hmac.new(secret.encode(), msg, hashlib.sha256).hexdigest()


@pytest.fixture
def app(tmp_path, monkeypatch):
    app = create_app({"TESTING": True, "DATABASE": str(tmp_path / "t.db"), "UPLOADS": str(tmp_path / "u"),
                      "RAZORPAY_KEY_ID": "rzp_test_dummy", "RAZORPAY_KEY_SECRET": "ks",
                      "RAZORPAY_WEBHOOK_SECRET": "ws"})
    count = iter(range(1, 99))
    monkeypatch.setattr(payments, "create_order", lambda amount, receipt: f"order_{next(count)}")
    return app


def query(app, sql, *args):
    with app.app_context():
        return get_db().execute(sql, args).fetchone()


def post(c, url, **data):
    page = c.get("/contact").get_data(as_text=True)
    data["csrf"] = re.search(r'name="csrf" value="(\w+)"', page).group(1)
    return c.post(url, data=data)


def customer(app, email="a@example.com"):
    c = app.test_client()
    post(c, "/register", name="A", email=email, password="password123")
    return c


def checkout(c, pid=5, method="razorpay"):
    post(c, f"/cart/add/{pid}")
    return post(c, "/checkout", method=method, **ADDRESS)


def stock(app, pid=5):
    return query(app, "SELECT stock FROM products WHERE id=?", pid)[0]


def order(app, oid=1):
    return query(app, "SELECT * FROM orders WHERE id=?", oid)


def hook(app, amount, secret="ws", rid="order_1"):
    body = json.dumps({"event": "payment.captured", "payload": {"payment": {"entity": {
        "id": "pay_1", "order_id": rid, "amount": amount, "currency": "INR"}}}}).encode()
    return app.test_client().post("/webhook/razorpay", data=body, content_type="application/json",
                                  headers={"X-Razorpay-Signature": sign(secret, body)})


def expire(app):
    query(app, "UPDATE orders SET created=datetime('now','-31 minutes')")
    app.test_client().get("/")


def test_pages_load(app):
    c = app.test_client()
    for url in ["/", "/?q=jhumka&sort=lo&max=1000", "/product/11", "/info", "/contact", "/cart", "/login", "/register"]:
        assert c.get(url).status_code == 200, url


def test_valid_signature_marks_paid(app):
    c = customer(app)
    assert checkout(c).location.endswith("/order/1/pay")
    assert order(app)["total"] == 97000 and stock(app) == 9
    assert "order_1" in c.get("/order/1/pay").get_data(as_text=True)
    assert "ks\"" not in c.get("/order/1/pay").get_data(as_text=True)
    post(c, "/order/1/verify", razorpay_payment_id="pay_1", razorpay_signature=sign("ks", b"order_1|pay_1"))
    assert order(app)["paid"] == 1 and order(app)["status"] == "placed"


def test_forged_signature_rejected(app):
    c = customer(app)
    checkout(c)
    post(c, "/order/1/verify", razorpay_payment_id="pay_1", razorpay_signature="forged")
    assert order(app)["paid"] == 0


def test_webhook_checks_signature_and_amount(app):
    checkout(customer(app))
    assert hook(app, 97000, secret="wrong").status_code == 400
    hook(app, 100)
    assert order(app)["paid"] == 0
    hook(app, 97000)
    hook(app, 97000)  # duplicate delivery
    assert order(app)["paid"] == 1 and stock(app) == 9


def test_unpaid_order_releases_stock_and_late_payment_retakes_it(app):
    checkout(customer(app))
    expire(app)
    assert order(app)["status"] == "cancelled" and stock(app) == 10
    hook(app, 97000)
    assert order(app)["status"] == "placed" and stock(app) == 9


def test_late_payment_without_stock_is_flagged(app):
    checkout(customer(app))
    expire(app)
    query(app, "UPDATE products SET stock=0 WHERE id=5")
    hook(app, 97000)
    assert order(app)["status"] == "cancelled" and "refund" in order(app)["note"] and stock(app) == 0


def test_gateway_failure_restores_stock(app, monkeypatch):
    def fail(*a):
        raise payments.PaymentError
    monkeypatch.setattr(payments, "create_order", fail)
    checkout(customer(app))
    assert order(app)["status"] == "cancelled" and stock(app) == 10


def test_cannot_oversell(app):
    c = customer(app)
    post(c, "/cart/add/5")
    query(app, "UPDATE products SET stock=0 WHERE id=5")
    post(c, "/checkout", method="cod", **ADDRESS)
    assert query(app, "SELECT COUNT(*) FROM orders")[0] == 0


def test_access_control(app):
    checkout(customer(app), method="cod")
    other = customer(app, "b@example.com")
    assert other.get("/order/1").status_code == 404
    assert other.get("/admin").status_code == 403
    assert app.test_client().post("/cart/add/5").status_code == 400  # no CSRF token


def test_admin_cancel_returns_stock_once(app):
    checkout(customer(app), method="cod")
    result = app.test_cli_runner().invoke(args=["create-admin", "--email", "admin@example.com", "--password", "adminpass1"])
    assert result.exit_code == 0, result.output
    admin = app.test_client()
    post(admin, "/login", email="admin@example.com", password="adminpass1")
    assert admin.get("/admin").status_code == 200
    assert admin.get("/admin/product/new").status_code == 200
    for _ in range(2):
        post(admin, "/admin/order/1", status="cancelled")
    assert stock(app) == 10
    post(admin, "/admin/product/5", name="X", category="Earrings", material="Silver", price="10", stock="3", active="1")
    assert stock(app) == 3
