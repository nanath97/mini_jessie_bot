# stripe_webhook.py

from fastapi import APIRouter, Request, Header
import stripe
import os
from datetime import datetime
from bott_webhook import paiements_recents  # nécessaire
from bott_webhook import log_to_airtable, bot, ADMIN_ID, groupe_contenus

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

        # 💥 NOUVEAU : gestion des paiements groupés
        metadata = session.get("metadata", {})
        groupe_id = metadata.get("groupe_id")
        user_id = metadata.get("user_id")

        if groupe_id and user_id:
            contenu = groupe_contenus.get(groupe_id)

            if contenu:
                try:
                    if contenu["type"] == "photo":
                        await bot.send_photo(int(user_id), contenu["file_id"])
                    elif contenu["type"] == "video":
                        await bot.send_video(int(user_id), contenu["file_id"])
                    elif contenu["type"] == "document":
                        await bot.send_document(int(user_id), contenu["file_id"])

                    print(f"✅ Contenu groupé {groupe_id} envoyé à {user_id}")

                    # Airtable + Notification admin
                    log_to_airtable(
                        pseudo="-",
                        user_id=user_id,
                        type_acces="groupé",
                        montant=montant,
                        contenu=f"Contenu groupé {groupe_id}",
                        email=session.get("customer_email", "inconnu")
                    )

                    await bot.send_message(
                        ADMIN_ID,
                        f"📢 Vente groupée de {montant}€ déverrouillée pour {user_id}"
                    )

                except Exception as e:
                    print(f"❌ Erreur envoi média groupé : {e}")
            else:
                await bot.send_message(
                    ADMIN_ID,
                    f"⚠️ Paiement reçu pour groupe {groupe_id}, mais aucun contenu n’a été trouvé."
                )

            return {"status": "ok"}

        # ✅ Paiement individuel classique (inchangé)
        paiements_recents[montant].append(datetime.now())
        print(f"✅ Paiement individuel détecté : {montant}€ enregistré")

    return {"status": "ok"}
