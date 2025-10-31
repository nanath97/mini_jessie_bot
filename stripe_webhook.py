# stripe_webhook.py

from fastapi import APIRouter, Request, Header
import stripe
import os
from bott_webhook import paiements_recents, contenus_en_attente, paiements_en_attente_par_user
from datetime import datetime
from core import log_to_airtable
from aiogram import Bot
from aiogram.types import ContentType

bot = Bot(token=os.getenv("BOT_TOKEN"))

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
        event = stripe.Webhook.construct_event(payload, stripe_signature, STRIPE_WEBHOOK_SECRET)
    except Exception as e:
        print(f"❌ Webhook Stripe invalide : {e}")
        return {"status": "invalid"}

    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        montant = int(session["amount_total"] / 100)
        user_id_stripe = session.get("client_reference_id")
        pseudo = session.get("customer_email") or "-"  # Adapté si l’email contient le pseudo

        print(f"✅ Paiement webhook reçu : {montant}€ pour {user_id_stripe}")

        try:
            user_id = int(user_id_stripe)
        except:
            print("❌ ID utilisateur Stripe invalide.")
            return {"status": "ignored"}

        # 🔐 Débloquer le contenu groupé (si en attente)
        if user_id in paiements_en_attente_par_user and user_id in contenus_en_attente:
            contenu = contenus_en_attente[user_id]
            try:
                if contenu["type"] == ContentType.PHOTO:
                    await bot.send_photo(chat_id=user_id, photo=contenu["file_id"], caption=contenu.get("caption"))
                elif contenu["type"] == ContentType.VIDEO:
                    await bot.send_video(chat_id=user_id, video=contenu["file_id"], caption=contenu.get("caption"))
                elif contenu["type"] == ContentType.DOCUMENT:
                    await bot.send_document(chat_id=user_id, document=contenu["file_id"], caption=contenu.get("caption"))
                print(f"✅ Contenu débloqué pour l’utilisateur {user_id}")
            except Exception as e:
                print(f"❌ Erreur lors de l’envoi du contenu débloqué : {e}")
            finally:
                contenus_en_attente.pop(user_id, None)
                paiements_en_attente_par_user.discard(user_id)

        # 🧾 Log dans Airtable
        try:
            log_to_airtable(
                pseudo=pseudo,
                user_id=user_id,
                type_acces="VIP",
                montant=montant,
                contenu="Paiement Telegram (groupé ou perso)"
            )
            print(f"📝 Paiement {montant}€ enregistré dans Airtable pour {pseudo} ({user_id})")
        except Exception as e:
            print(f"❌ Erreur Airtable : {e}")

        # 🔁 Historique interne
        paiements_recents[montant].append(datetime.now())

    return {"status": "ok"}
