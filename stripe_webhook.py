# stripe_webhook.py

from fastapi import APIRouter, Request, Header
import stripe
import os
from bott_webhook import paiements_recents, authorized_users, bot
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

    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        montant = int(session["amount_total"] / 100)
        paiements_recents[montant].append(datetime.now())
        print(f"✅ Paiement webhook : {montant}€ enregistré à {datetime.now().isoformat()}")

        # ici on récupère l'ID Telegram via metadata (si tu l’ajoutes dans Stripe)
        user_id = session.get("metadata", {}).get("telegram_id")

        if user_id:
            authorized_users.add(int(user_id))
            print(f"👑 Nouveau VIP confirmé : {user_id}")

            # création automatique du topic staff
            try:
                import staff_system
                if staff_system.STAFF_FEATURE_ENABLED:
                    await staff_system.ensure_topic_for(
                        bot,
                        user_id=int(user_id),
                        username=session.get("customer_email", "").split("@")[0],
                        email=session.get("customer_email", ""),
                        total_spent=montant
                    )
            except Exception as e:
                print(f"[staff] ensure_topic_for error: {e}")

    return {"status": "ok"}
