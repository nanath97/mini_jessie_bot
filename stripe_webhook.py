# stripe_webhook.py

from fastapi import APIRouter, Request, Header
import stripe
import os
import requests
from bott_webhook import paiements_recents  # stockage des paiements récents
from datetime import datetime

router = APIRouter()

stripe.api_key = os.getenv("STRIPE_SECRET_KEY")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET")

AIRTABLE_API_KEY = os.getenv("AIRTABLE_API_KEY")
BASE_ID = os.getenv("BASE_ID")
PAYMENT_LINKS_TABLE = "Payment Links"


def mark_payment_link_as_paid(amount_cents: int):
    """
    Met à jour dans Airtable la dernière ligne 'Pending'
    correspondant au montant payé en Stripe.
    """
    try:
        url = f"https://api.airtable.com/v0/{BASE_ID}/{PAYMENT_LINKS_TABLE.replace(' ', '%20')}"
        headers = {
            "Authorization": f"Bearer {AIRTABLE_API_KEY}",
            "Content-Type": "application/json"
        }

        # Recherche des paiements Pending avec ce montant
        formula = f"AND({{Status}}='Pending', {{Amount Cents}}={amount_cents})"

        resp = requests.get(url, headers=headers, params={"filterByFormula": formula})
        records = resp.json().get("records", [])

        if not records:
            print(f"[AIRTABLE] Aucun paiement Pending trouvé pour {amount_cents} cents")
            return

        # On prend la première correspondance (dernière logique du funnel)
        record_id = records[0]["id"]

        patch_url = f"{url}/{record_id}"
        update_resp = requests.patch(
            patch_url,
            headers=headers,
            json={"fields": {"Status": "Paid"}}
        )

        if update_resp.status_code not in (200, 201):
            print(f"[AIRTABLE] Erreur update Paid : {update_resp.text}")
        else:
            print(f"[AIRTABLE] Paiement {amount_cents} marqué comme Paid")

    except Exception as e:
        print(f"[AIRTABLE] Exception update Paid : {e}")


@router.get("/stripe/test")
async def test_stripe_route():
    return {"status": "ok"}


@router.post("/stripe/webhook")
async def stripe_webhook(request: Request, stripe_signature: str = Header(None)):
    payload = await request.body()

    try:
        event = stripe.Webhook.construct_event(
            payload, stripe_signature, STRIPE_WEBHOOK_SECRET
        )
    except Exception as e:
        print(f"❌ Webhook Stripe invalide : {e}")
        return {"status": "invalid"}

    # ===============================
    # PAIEMENT VALIDÉ STRIPE
    # ===============================
    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]

        # Montant en centimes (ex: 250 pour 2,50€)
        montant_cents = session["amount_total"]

        # Sécurité : créer la liste si elle n'existe pas
        if montant_cents not in paiements_recents:
            paiements_recents[montant_cents] = []

        paiements_recents[montant_cents].append(datetime.now())

        # 🔥 MISE À JOUR AIRTABLE (Pending -> Paid)
        mark_payment_link_as_paid(montant_cents)

        # Affichage lisible en euros
        montant_euros = montant_cents / 100

        print(
            f"✅ Paiement webhook : {montant_euros:.2f}€ "
            f"(={montant_cents} cents) enregistré à {datetime.now().isoformat()}"
        )

    return {"status": "ok"}
