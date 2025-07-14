# stripe_webhook.py

from fastapi import APIRouter, Request, Header
import stripe
import os
from datetime import datetime
from bott_webhook import paiements_recents  # nécessaire

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

    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        montant = int(session["amount_total"] / 100)

        # 🧠 Liste des montants utilisés uniquement pour les ventes groupées
        PRIX_GROUPE = [1, 9, 14, 19, 24, 29, 34, 39, 49, 59, 69, 79, 89, 99]

        if montant in PRIX_GROUPE:
            from bott_webhook import log_to_airtable
            log_to_airtable(
                pseudo="-",
                user_id="-",
                type_acces="groupé",
                montant=montant,
                contenu="Contenu groupé",
                email=session.get("customer_email", "vinteo.ac@.com")
            )
            print(f"✅ Vente groupée de {montant}€ ajoutée à Airtable")
        else:
            paiements_recents[montant].append(datetime.now())
            print(f"✅ Paiement individuel détecté : {montant}€ enregistré")

    return {"status": "ok"}
