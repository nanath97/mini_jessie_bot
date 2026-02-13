from fastapi import FastAPI, Request
from aiogram import types, Bot, Dispatcher
from dotenv import load_dotenv
import os
import asyncio
import requests
from pydantic import BaseModel

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
    telegram_id: int
    payment_link: str
    message: str

@app.post("/reminder")
async def send_reminder(payload: ReminderPayload):
    try:
        text = f"{payload.message}\n\n💳 Payer ici : {payload.payment_link}"

        telegram_api_url = f"https://api.telegram.org/bot{os.getenv('BOT_TOKEN')}/sendMessage"

        response = requests.post(
            telegram_api_url,
            json={
                "chat_id": payload.telegram_id,
                "text": text
            }
        )

        print("[REMINDER] Message envoyé :", response.text)

        return {
            "status": "sent",
            "telegram_response": response.json()
        }

    except Exception as e:
        print("[REMINDER ERROR]", e)
        return {
            "status": "error",
            "error": str(e)
        }


# ---------------------------
# STARTUP EVENT
# ---------------------------
@app.on_event("startup")
async def startup_event():
    try:
        # 1) Recharge les VIP dans authorized_users
        try:
            bott_webhook.initialize_authorized_users()
        except Exception as e:
            print(f"[STARTUP] Warning: initialize_authorized_users a échoué : {e}")

        # 2) Recharge les Topic IDs depuis Airtable (source de vérité)
        await load_vip_topics_from_airtable()

        # 3) Recharge les annotations + panneaux locaux depuis disque (fallback local)
        load_vip_topics_from_disk()

        # 4) Recharge les annotations depuis la table Airtable (AnnotationsVIP)
        try:
            load_annotations_from_airtable()
        except Exception as e:
            print(f"[ANNOTATION] Échec chargement Airtable : {e}")

        # 5) Démarre le scheduler en tâche de fond
        try:
            asyncio.create_task(bott_webhook.scheduler_loop())
            print("[STARTUP] Scheduler Loop démarré.")
        except Exception as e:
            print(f"[STARTUP] Impossible de démarrer le scheduler : {e}")

        print("[STARTUP] VIP + topics + annotations initialisés.")

    except Exception as e:
        print(f"[STARTUP ERROR] Erreur pendant le chargement des VIP : {e}")


# ---------------------------
# STRIPE WEBHOOK
# ---------------------------
app.include_router(stripe_router)

print("🔥 >>> FICHIER MAIN.PY BIEN LANCÉ <<< 🔥")
