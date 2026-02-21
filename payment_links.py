import os
import requests
from datetime import datetime
import stripe

# Variables d'environnement
STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY")
AIRTABLE_API_KEY = os.getenv("AIRTABLE_API_KEY")
BASE_ID = os.getenv("BASE_ID")

stripe.api_key = STRIPE_SECRET_KEY


def create_dynamic_checkout(amount_cents: int, client_key: str, content_id: str, admin_id: str = ""):
    """
    Crée une session Stripe Checkout dynamique avec metadata (indispensable pour unlock).
    Retourne (session_url, session_id).
    """
    success_url = os.getenv("PWA_SUCCESS_URL")
    cancel_url = os.getenv("PWA_CANCEL_URL")

    if not success_url or not cancel_url:
        raise RuntimeError("Missing PWA_SUCCESS_URL or PWA_CANCEL_URL in environment variables")

    session = stripe.checkout.Session.create(
        payment_method_types=["card"],
        line_items=[{
            "price_data": {
                "currency": "eur",
                "product_data": {"name": "Paiement NovaPulse"},
                "unit_amount": int(amount_cents),
            },
            "quantity": 1,
        }],
        mode="payment",

        # IMPORTANT: redirection vers PWA
        success_url=f"{success_url}?paid=1&session_id={{CHECKOUT_SESSION_ID}}",
        cancel_url=cancel_url,

        metadata={
            "channel": "pwa",
            "client_key": str(client_key),
            "content_id": str(content_id),
            "admin_id": str(admin_id or ""),
            "amount_cents": str(int(amount_cents)),
        },
    )

    return session.url, session.id


def save_payment_link_to_airtable(*, client_key: str, content_id: str, payment_link: str,
                                  admin_id: str, amount_cents: int, checkout_session_id: str):
    """
    Crée une ligne Airtable "Payment Links" en statut Pending,
    avec les 3 champs clés: Client Key / Content ID / Checkout Session ID.
    """
    table = "Payment Links"
    url = f"https://api.airtable.com/v0/{BASE_ID}/{table.replace(' ', '%20')}"
    headers = {
        "Authorization": f"Bearer {AIRTABLE_API_KEY}",
        "Content-Type": "application/json"
    }

    data = {
        "fields": {
            "Payment Link URL": payment_link,
            "Client Key": str(client_key),
            "Content ID": str(content_id),
            "Checkout Session ID": str(checkout_session_id),

            "ADMIN ID": str(admin_id),
            "Amount Cents": int(amount_cents),
            "URL Render": os.getenv("RENDER_WEBHOOK_HOST"),
            "Status": "Pending",
            "Sent At": datetime.utcnow().isoformat()
        }
    }

    resp = requests.post(url, json=data, headers=headers)
    print("[AIRTABLE SAVE]", resp.status_code, resp.text)
    return resp