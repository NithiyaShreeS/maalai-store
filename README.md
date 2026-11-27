# Maalai Jewels store

Flask + SQLite jewellery shop with Razorpay checkout.

## Run it
    python -m venv venv
    venv\Scripts\activate          # Windows (macOS/Linux: source venv/bin/activate)
    pip install -r requirements.txt
    copy .env.example .env         # macOS/Linux: cp .env.example .env
    flask --app app create-admin
    python app.py                  # http://127.0.0.1:5000

The database and 15 sample products are created on first start.

## Turn on Razorpay (test mode first)
1. In the Razorpay Dashboard, switch to Test Mode and generate API keys.
2. Put the Key ID and Key Secret in `.env`, then restart.
3. Check out and choose "Pay online". Test UPI IDs: `success@razorpay`, `failure@razorpay`.
4. Webhook (needs a public HTTPS address): add `https://YOUR-DOMAIN/webhook/razorpay`,
   events `payment.captured` and `order.paid`, and put its secret in `.env`.
   The webhook records payments when the customer closes the browser too early.

## How payment is protected
- Prices and totals are calculated on the server.
- The server creates the Razorpay order; the key secret never reaches the browser.
- A payment counts only after its HMAC-SHA256 signature is verified.
- Webhooks are signature-checked and must match the order amount.
- Stock is held for 30 minutes while payment is pending.

## Before going live
- Replace sample products, store name, policies and size charts.
- Host with a production server (not `python app.py`), HTTPS and `HTTPS=1`; back up `instance/`.
- Add privacy, terms, refund and contact pages with the seller's real details.
- Complete Razorpay account activation and use live keys.
- Not included: email/SMS, password reset, automatic refunds, GST invoices.

## Tests
    python -m pytest -q
