# stripe_webhook.py

from fastapi import APIRouter, Request, Header
import stripe
import os
from core import bot
from aiogram import types
from bott_webhook import authorized_users, contenus_en_attente, paiements_en_attente_par_user, log_to_airtable, ADMIN_ID

router = APIRouter()

stripe.api_key = os.getenv("STRIPE_SECRET_KEY")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET")

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
        user_id = session.get("client_reference_id")

        if not user_id:
            print("❌ client_reference_id manquant")
            return {"status": "missing"}

        try:
            user_id = int(user_id)
        except ValueError:
            print("❌ ID Telegram invalide")
            return {"status": "invalid_id"}

        montant = int(session["amount_total"] / 100)

        # Autoriser l'utilisateur
        authorized_users.add(user_id)

        # Enregistrement dans Airtable
        log_to_airtable(
            pseudo="Stripe",
            user_id=user_id,
            type_acces="Paiement",
            montant=montant,
            contenu="Paiement via Stripe webhook",
        )

        # Livraison du contenu si déjà prêt
        if user_id in contenus_en_attente:
            contenu = contenus_en_attente[user_id]
            if contenu["type"] == types.ContentType.PHOTO:
                await bot.send_photo(chat_id=user_id, photo=contenu["file_id"], caption=contenu["caption"])
            elif contenu["type"] == types.ContentType.VIDEO:
                await bot.send_video(chat_id=user_id, video=contenu["file_id"], caption=contenu["caption"])
            elif contenu["type"] == types.ContentType.DOCUMENT:
                await bot.send_document(chat_id=user_id, document=contenu["file_id"], caption=contenu["caption"])
            del contenus_en_attente[user_id]
        else:
            paiements_en_attente_par_user.add(user_id)

        await bot.send_message(user_id, f"✅ Merci pour ton paiement de {montant}€ 💖 ! Ton contenu arrive dans quelques secondes...")
        await bot.send_message(ADMIN_ID, f"💰 Paiement confirmé Stripe (webhook) : {montant}€ – user_id {user_id}")

    return {"status": "ok"}
