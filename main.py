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

# Mapping vendeur (admin Telegram) -> seller_slug Airtable
ADMIN_TO_SLUG = {
    7334072965: "coach-matthieu",
    # ajouter ici les autres vendeurs
}

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

        Bot.set_current(bot)
        Dispatcher.set_current(dp)

        await dp.process_update(update)
    except Exception as e:
        print("❌ Erreur dans webhook :", e)
        return {"ok": False, "error": str(e)}
    return {"ok": True}


# ---------------------------
# EMAIL + SLUG → TOPIC ID (Airtable)
# ---------------------------
def find_topic_id_by_email_and_slug(email: str, seller_slug: str):
    AIRTABLE_API_KEY = os.getenv("AIRTABLE_API_KEY")
    BASE_ID = os.getenv("BASE_ID")
    TABLE_NAME = "PWA Clients"

    print("[AIRTABLE QUERY] email:", email)
    print("[AIRTABLE QUERY] slug:", seller_slug)

    url = f"https://api.airtable.com/v0/{BASE_ID}/{TABLE_NAME.replace(' ', '%20')}"
    headers = {"Authorization": f"Bearer {AIRTABLE_API_KEY}"}

    formula = f"AND(LOWER({{email}})='{email.lower()}', {{seller_slug}}='{seller_slug}')"
    print("[AIRTABLE QUERY] formula:", formula)

    params = {"filterByFormula": formula}

    try:
        resp = requests.get(url, headers=headers, params=params, timeout=10)
        data = resp.json()
        print("[AIRTABLE QUERY] response:", data)
    except Exception as e:
        print("[AIRTABLE QUERY ERROR]", e)
        return None

    records = data.get("records", [])
    if not records:
        print("[AIRTABLE QUERY] Aucun record trouvé.")
        return None

    topic_id = records[0]["fields"].get("topic_id")
    print("[AIRTABLE QUERY] topic_id trouvé:", topic_id)
    return topic_id


# ---------------------------
# REMINDER ROUTE (POUR AIRTABLE)
# ---------------------------
class ReminderPayload(BaseModel):
    client_key: str
    admin_id: int
    payment_link: str
    message: str


@app.post("/reminder")
async def send_reminder(payload: ReminderPayload):
    try:
        print("\n================ REMINDER DEBUG ================")
        print("[REMINDER] Payload reçu :", payload.dict())

        client_email = payload.client_key.lower().strip()
        admin_id = payload.admin_id
        text = payload.message

        print("[REMINDER] Email normalisé :", client_email)
        print("[REMINDER] Admin ID :", admin_id)

        seller_slug = ADMIN_TO_SLUG.get(admin_id)
        print("[REMINDER] Seller slug résolu :", seller_slug)

        if not seller_slug:
            print("[REMINDER ERROR] Aucun seller_slug pour cet admin.")
            return {"status": "error", "error": f"Aucun seller_slug pour admin_id={admin_id}"}

        topic_id = find_topic_id_by_email_and_slug(client_email, seller_slug)

        if not topic_id:
            print("[REMINDER ERROR] Aucun topic trouvé.")
            admin_alert = int(os.getenv("ADMIN_TELEGRAM_ID", "7334072965"))
            await bot.send_message(
                chat_id=admin_alert,
                text=(
                    "❌ Relance impossible\n\n"
                    f"Email : {client_email}\n"
                    f"Seller : {seller_slug}\n"
                    "Aucun topic trouvé dans Airtable."
                )
            )
            return {"status": "error", "error": "topic not found"}

        staff_group_id = int(os.getenv("STAFF_GROUP_ID"))
        print("[REMINDER] Envoi vers STAFF_GROUP_ID:", staff_group_id)
        print("[REMINDER] Envoi vers topic_id:", topic_id)

        try:
            await bot.send_message(
                chat_id=staff_group_id,
                message_thread_id=int(topic_id),
                text=text
            )
            print("[REMINDER] Message envoyé avec succès dans le topic.")
        except Exception as e:
            print("[REMINDER TELEGRAM ERROR]", e)
            return {"status": "error", "error": str(e)}

        print("================ END REMINDER DEBUG ================\n")
        return {"status": "sent", "topic_id": topic_id}

    except Exception as e:
        print("[REMINDER FATAL ERROR]", e)
        return {"status": "error", "error": str(e)}


# ---------------------------
# STARTUP EVENT
# ---------------------------
@app.on_event("startup")
async def startup_event():
    try:
        print("🚀 Startup NovaPulse...")

        try:
            bott_webhook.initialize_authorized_users()
        except Exception as e:
            print(f"[STARTUP] Warning: initialize_authorized_users a échoué : {e}")

        await load_vip_topics_from_airtable()
        load_vip_topics_from_disk()

        try:
            load_annotations_from_airtable()
        except Exception as e:
            print(f"[ANNOTATION] Échec chargement Airtable : {e}")

        try:
            await restore_missing_panels()
            print("[STARTUP] restore_missing_panels exécuté.")
        except Exception as e:
            print(f"[STARTUP] Erreur restore_missing_panels : {e}")

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
    try:
        amount_raw = data.get("amount_cents")
        email = data.get("email")
        seller_slug = data.get("seller_slug")

        print("[CHECKOUT] email:", email)
        print("[CHECKOUT] seller_slug:", seller_slug)
        print("[CHECKOUT] amount_cents:", amount_raw)

        if amount_raw is None or not email:
            return {"status": "error", "message": "amount_cents ou email manquant"}

        amount = int(amount_raw)

        checkout_url = create_dynamic_checkout(amount)
        admin_id = int(os.getenv("ADMIN_TELEGRAM_ID", "7334072965"))

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

print("🔥 >>> FICHIER MAIN.PY BIEN LANCÉ AVEC DEBUG <<< 🔥")