import os
import requests
from datetime import datetime
import stripe

# Variables d'environnement
STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY")
BOT_USERNAME = os.getenv("BOT_USERNAME")
AIRTABLE_API_KEY = os.getenv("AIRTABLE_API_KEY")
BASE_ID = os.getenv("BASE_ID")

stripe.api_key = STRIPE_SECRET_KEY


def create_dynamic_checkout(amount_cents: int):
    """
    Crée une session Stripe Checkout dynamique
    """
    session = stripe.checkout.Session.create(
        payment_method_types=["card"],
        line_items=[{
            "price_data": {
                "currency": "eur",
                "product_data": {
                    "name": "Paiement NovaPulse"
                },
                "unit_amount": amount_cents,
            },
            "quantity": 1,
        }],
        mode="payment",
        success_url=f"https://t.me/{BOT_USERNAME}?start=cdan{amount_cents}",
        cancel_url=f"https://t.me/{BOT_USERNAME}",
    )

    return session.url


def save_payment_link_to_airtable(client_telegram_id, payment_link, admin_id, amount_cents):
    """
    Crée une ligne 'Payment Links' en statut Pending dans Airtable.
    Compatible Telegram ET PWA (email stocké dans ID Telegram).
    """

    AIRTABLE_TABLE_PAYMENT_LINKS = "Payment Links"

    url = f"https://api.airtable.com/v0/{BASE_ID}/{AIRTABLE_TABLE_PAYMENT_LINKS.replace(' ', '%20')}"

    headers = {
        "Authorization": f"Bearer {AIRTABLE_API_KEY}",
        "Content-Type": "application/json"
    }

    data = {
        "fields": {
            "Payment Link URL": payment_link,
            "ID Telegram": str(client_telegram_id),  # Telegram ID ou email PWA
            "ADMIN ID": str(admin_id),
            "Amount Cents": amount_cents,
            "URL Render": os.getenv("RENDER_WEBHOOK_HOST"),
            "Status": "Pending",
            "Sent At": datetime.utcnow().isoformat()
        }
    }

    response = requests.post(url, json=data, headers=headers)
    print("[AIRTABLE SAVE]", response.status_code, response.text)
