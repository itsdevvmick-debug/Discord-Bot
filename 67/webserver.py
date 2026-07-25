from flask import Flask
from threading import Thread
from flask import request, abort, redirect
import json
import logging

try:
    import stripe
except Exception:
    stripe = None

from config import Config

app = Flask('')

@app.route('/')
def home():
    return f"{Config.BRAND_NAME} bot is alive!"

def run():
    app.run(host='0.0.0.0', port=Config.RENDER_PORT, use_reloader=False)

def keep_alive():
    t = Thread(target=run, daemon=True)
    t.start()


@app.route('/create-checkout')
def create_checkout():
    """Create a Stripe Checkout session for a product and redirect the user to Stripe."""
    if stripe is None:
        return "Stripe library not installed", 500

    product_id = request.args.get('product_id')
    user_id = request.args.get('user_id')
    if not product_id or not user_id:
        return "Missing product_id or user_id", 400

    try:
        # Load product info from the database module
        from database import db
        prod = None
        import asyncio
        loop = asyncio.new_event_loop()
        prod = loop.run_until_complete(db.fetch_product_by_id(int(product_id)))
        loop.close()

        if not prod:
            return "Product not found", 404

        price = float(prod['price'] or 0)
        # create Checkout session
        stripe.api_key = Config.STRIPE_API_KEY
        session = stripe.checkout.Session.create(
            payment_method_types=['card'],
            line_items=[{
                'price_data': {
                    'currency': 'usd',
                    'product_data': {'name': prod['name']},
                    'unit_amount': int(price * 100),
                },
                'quantity': 1,
            }],
            mode='payment',
            success_url=Config.STRIPE_SUCCESS_URL,
            cancel_url=Config.STRIPE_CANCEL_URL,
            metadata={'product_id': str(product_id), 'discord_user_id': str(user_id)},
        )

        return redirect(session.url, code=302)
    except Exception as exc:
        logging.exception("Error creating checkout session: %s", exc)
        return "Internal error", 500


@app.route('/stripe/webhook', methods=['POST'])
def stripe_webhook():
    if stripe is None:
        return "Stripe library not installed", 500

    payload = request.get_data()
    sig_header = request.headers.get('stripe-signature')
    webhook_secret = Config.STRIPE_WEBHOOK_SECRET

    try:
        event = stripe.Webhook.construct_event(payload, sig_header, webhook_secret) if webhook_secret else json.loads(payload)
    except Exception as e:
        logging.exception('Webhook signature verification failed: %s', e)
        return abort(400)

    # Handle the checkout.session.completed event
    if event['type'] == 'checkout.session.completed':
        session = event['data']['object']
        metadata = session.get('metadata', {})
        product_id = metadata.get('product_id')
        discord_user_id = metadata.get('discord_user_id')
        transaction_id = session.get('id')

        # Record the purchase in the database
        try:
            from database import db
            import asyncio
            loop = asyncio.new_event_loop()
            loop.run_until_complete(db.add_purchase(int(product_id), int(discord_user_id), 'stripe', transaction_id, 'completed'))
            loop.close()
        except Exception:
            logging.exception('Failed to record purchase from webhook')

    return '', 200
