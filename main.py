from fastapi import FastAPI, Request, Body
from aiogram import types, Bot, Dispatcher
from dotenv import load_dotenv
import os
import asyncio
import requests
from pydantic import BaseModel

from payment_links import create_dynamic_checkout, save_payment_link_to_airtable
from core import bot, dp
import bott_webhook
from stripe_webhook import router as stripe_router
from vip_topics import (
    load_vip_topics_from_airtable,
    load_vip_topics_from_disk,
    restore_missing_panels,
    load_annotations_from_airtable
)

load_dotenv()
app = FastAPI()

# ---------------------------
# TELEGRAM WEBHOOK
# ---------------------------
@app.post(f"/bot/{os.getenv('BOT_TOKEN')}")
async def telegram_webhook(request: Request):
    try:
        data = await request.json()
        update = types.Update(**data)

        # Fix context Aiogram
        Bot.set_current(bot)
        Dispatcher.set_current(dp)

        await dp.process_update(update)
    except Exception as e:
        print("Erreur dans webhook :", e)
        return {"ok": False, "error": str(e)}
    return {"ok": True}


# ---------------------------
# REMINDER ROUTE (POUR AIRTABLE)
# ---------------------------
class ReminderPayload(BaseModel):
    client_key: str   # email du client = identifiant PWA
    payment_link: str
    message: str

from vip_topics import vip_topics  # dict: {email: {"topic_id": int, ...}}

@app.post("/reminder")
async def send_reminder(payload: ReminderPayload):
    try:
        client_email = payload.client_key.lower().strip()
        text = payload.message

        # 1️⃣ Trouver le topic du client via son email (client_key)
        client_data = vip_topics.get(client_email)
        if not client_data:
            return {
                "status": "error",
                "error": f"Client introuvable pour email={client_email}"
            }

        topic_id = client_data.get("topic_id")
        if not topic_id:
            return {
                "status": "error",
                "error": f"topic_id manquant pour email={client_email}"
            }

        staff_group_id = int(os.getenv("STAFF_GROUP_ID"))

        # 2️⃣ Envoyer la relance dans le topic (visible dans la PWA)
        await bot.send_message(
            chat_id=staff_group_id,
            message_thread_id=topic_id,
            text=text
        )

        # 3️⃣ Notifier l’admin vendeur
        admin_id = int(os.getenv("ADMIN_TELEGRAM_ID", "7334072965"))
        await bot.send_message(
            chat_id=admin_id,
            text=(
                "🔔 Relance automatique envoyée\n\n"
                f"👤 Client : {client_email}\n"
                f"🧵 Topic ID : {topic_id}\n"
                f"🔗 Paiement : relance pending"
            )
        )

        return {
            "status": "sent",
            "client": client_email,
            "topic_id": topic_id
        }

    except Exception as e:
        print("[REMINDER ERROR]", e)
        return {"status": "error", "error": str(e)}

# ---------------------------
# STARTUP EVENT
# ---------------------------
@app.on_event("startup")
async def startup_event():
    try:
        # 1) Recharge les VIP
        try:
            bott_webhook.initialize_authorized_users()
        except Exception as e:
            print(f"[STARTUP] Warning: initialize_authorized_users a échoué : {e}")

        # 2) Recharge les topics VIP depuis Airtable
        await load_vip_topics_from_airtable()

        # 3) Recharge fallback local
        load_vip_topics_from_disk()

        # 4) Recharge annotations
        try:
            load_annotations_from_airtable()
        except Exception as e:
            print(f"[ANNOTATION] Échec chargement Airtable : {e}")

        # 5) Restaure panels manquants
        try:
            await restore_missing_panels()
            print("[STARTUP] restore_missing_panels exécuté.")
        except Exception as e:
            print(f"[STARTUP] Erreur restore_missing_panels : {e}")

        # 6) Scheduler relances
        try:
            asyncio.create_task(bott_webhook.scheduler_loop())
            print("[STARTUP] Scheduler Loop démarré.")
        except Exception as e:
            print(f"[STARTUP] Impossible de démarrer le scheduler : {e}")

        print("[STARTUP] VIP + topics + annotations + panels initialisés.")

    except Exception as e:
        print(f"[STARTUP ERROR] Erreur pendant le chargement des VIP : {e}")


# ---------------------------
# CREATE CHECKOUT (PWA → BOT)
# ---------------------------
@app.post("/create-checkout")
async def create_checkout(data: dict = Body(...)):
    """
    Création d'un paiement dynamique NovaPulse (PWA)
    → crée Stripe
    → crée ligne Airtable Pending (comme /envXX)
    """
    try:
        amount_raw = data.get("amount_cents")
        email = data.get("email")           # stocké dans "ID Telegram"
        seller_slug = data.get("seller_slug")

        if amount_raw is None or not email:
            return {"status": "error", "message": "amount_cents ou email manquant"}

        amount = int(amount_raw)

        # 1️⃣ Création lien Stripe
        checkout_url = create_dynamic_checkout(amount)

        # 2️⃣ ADMIN vendeur (Telegram)
        admin_id = int(os.getenv("ADMIN_TELEGRAM_ID", "7334072965"))

        # 3️⃣ Création ligne Airtable Pending
        save_payment_link_to_airtable(
            client_telegram_id=email,
            payment_link=checkout_url,
            admin_id=admin_id,
            amount_cents=amount
        )

        print(f"[PWA PAYMENT] Pending créé pour {email}:{seller_slug} - {amount} cents")

        return {
            "status": "success",
            "checkout_url": checkout_url,
            "client_uid": f"{email}:{seller_slug}"
        }

    except Exception as e:
        print("❌ Erreur create_checkout:", e)
        return {"status": "error", "message": str(e)}


# ---------------------------
# STRIPE WEBHOOK
# ---------------------------
app.include_router(stripe_router)

print("🔥 >>> FICHIER MAIN.PY BIEN LANCÉ <<< 🔥")
