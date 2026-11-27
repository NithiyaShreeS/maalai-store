"""Razorpay calls and signature checks. The key secret never leaves the server."""
import hashlib
import hmac

import requests
from flask import current_app

API = "https://api.razorpay.com/v1"


class PaymentError(Exception):
    pass


def configured():
    c = current_app.config
    return bool(c["RAZORPAY_KEY_ID"] and c["RAZORPAY_KEY_SECRET"])



def create_order(amount_paise, receipt):
    c = current_app.config

    try:
        r = requests.post(
            f"{API}/orders",
            auth=(
                c["RAZORPAY_KEY_ID"].strip(),
                c["RAZORPAY_KEY_SECRET"].strip()
            ),
            json={
                "amount": int(amount_paise),
                "currency": "INR",
                "receipt": receipt
            },
            timeout=20
        )

        if not r.ok:
            current_app.logger.error(
                "Razorpay response status: %s",
                r.status_code
            )
            current_app.logger.error(
                "Razorpay response body: %s",
                r.text[:2000]
            )

        r.raise_for_status()
        return r.json()["id"]

    except (requests.RequestException, KeyError, ValueError) as e:
        current_app.logger.exception(
            "Razorpay order creation failed"
        )
        raise PaymentError from e



def _matches(secret, message, signature):
    if not secret or not signature:
        return False
    expected = hmac.new(secret.encode(), message, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected.encode(), signature.encode())


def valid_payment(order_id, payment_id, signature):
    return _matches(current_app.config["RAZORPAY_KEY_SECRET"],
                    f"{order_id}|{payment_id}".encode(), signature)


def valid_webhook(raw_body, signature):
    return _matches(current_app.config["RAZORPAY_WEBHOOK_SECRET"], raw_body, signature)
