# stripe_webhook.py

from fastapi import APIRouter, Request, Header
import stripe
import os
from bott_webhook import paiements_recents  # stockage des paiements récents
from datetime import datetime

router = APIRouter()

stripe.api_key = os.getenv("STRIPE_SECRET_KEY")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET")


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

        # Affichage lisible en euros
        montant_euros = montant_cents / 100

        print(
            f"✅ Paiement webhook : {montant_euros:.2f}€ "
            f"(={montant_cents} cents) enregistré à {datetime.now().isoformat()}"
        )

    return {"status": "ok"}
