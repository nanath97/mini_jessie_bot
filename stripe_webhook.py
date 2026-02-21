# stripe_webhook.py

from fastapi import APIRouter, Request, Header
import stripe
import os
import requests
from datetime import datetime

router = APIRouter()

stripe.api_key = os.getenv("STRIPE_SECRET_KEY")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET")

AIRTABLE_API_KEY = os.getenv("AIRTABLE_API_KEY")
BASE_ID = os.getenv("BASE_ID")
PAYMENT_LINKS_TABLE = "Payment Links"


def mark_payment_link_as_paid_by_session(checkout_session_id: str):
    """
    Met à jour dans Airtable la ligne Pending correspondant au Checkout Session ID.
    """
    try:
        url = f"https://api.airtable.com/v0/{BASE_ID}/{PAYMENT_LINKS_TABLE.replace(' ', '%20')}"
        headers = {
            "Authorization": f"Bearer {AIRTABLE_API_KEY}",
            "Content-Type": "application/json"
        }

        formula = f"{{Checkout Session ID}}='{checkout_session_id}'"
        resp = requests.get(url, headers=headers, params={"filterByFormula": formula})
        records = resp.json().get("records", [])
        if not records:
            print(f"[AIRTABLE] Aucun Pending trouvé pour session_id={checkout_session_id}")
            return None

        record_id = records[0]["id"]
        patch_url = f"{url}/{record_id}"

        update_resp = requests.patch(
            patch_url,
            headers=headers,
            json={
                "fields": {
                    "Status": "Paid",
                    "Paid At": datetime.utcnow().isoformat()
                }
            }
        )

        if update_resp.status_code not in (200, 201):
            print(f"[AIRTABLE] Erreur update Paid : {update_resp.text}")
            return None

        print(f"[AIRTABLE] session_id={checkout_session_id} marqué Paid")
        return record_id

    except Exception as e:
        print(f"[AIRTABLE] Exception update Paid : {e}")
        return None


@router.post("/stripe/webhook")
async def stripe_webhook(request: Request, stripe_signature: str = Header(None)):
    payload = await request.body()

    # 1) Vérification signature Stripe (sécurité)
    try:
        event = stripe.Webhook.construct_event(
            payload=payload,
            sig_header=stripe_signature,
            secret=STRIPE_WEBHOOK_SECRET
        )
    except Exception as e:
        print(f"❌ Webhook Stripe invalide : {e}")
        return {"status": "invalid"}

    # 2) Traitement event
    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]

        checkout_session_id = session.get("id")
        montant_cents = session.get("amount_total")
        metadata = session.get("metadata", {}) or {}

        client_key = metadata.get("client_key")
        content_id = metadata.get("content_id")
        channel = metadata.get("channel")

        print(
            f"✅ Stripe paid: session={checkout_session_id} amount={montant_cents} "
            f"client={client_key} content={content_id} channel={channel}"
        )

        # 3) Update Airtable via session_id (fiable)
        mark_payment_link_as_paid_by_session(checkout_session_id)

        # 4) Plus tard: déclenchement unlock PWA (on le fera à l'étape suivante)

    return {"status": "ok"}