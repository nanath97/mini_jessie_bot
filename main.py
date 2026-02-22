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

# Mapping admin → seller_slug
ADMIN_TO_SLUG = {
    7334072965: "coach-matthieu",
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
# FIND TOPIC FROM AIRTABLE (PWA CLIENTS)
# ---------------------------
def find_topic_id_by_email_and_slug(email: str, seller_slug: str):
    AIRTABLE_API_KEY = os.getenv("AIRTABLE_API_KEY")
    BASE_ID = os.getenv("BASE_ID")
    TABLE_NAME = "PWA Clients"

    url = f"https://api.airtable.com/v0/{BASE_ID}/{TABLE_NAME.replace(' ', '%20')}"
    headers = {"Authorization": f"Bearer {AIRTABLE_API_KEY}"}

    formula = f"AND(LOWER({{email}})='{email.lower()}', {{seller_slug}}='{seller_slug}')"
    params = {"filterByFormula": formula}

    print(f"[DEBUG] Airtable lookup formula = {formula}")

    resp = requests.get(url, headers=headers, params=params)
    data = resp.json()

    print(f"[DEBUG] Airtable response = {data}")

    records = data.get("records", [])
    if not records:
        print("[DEBUG] Aucun record trouvé dans Airtable")
        return None

    topic_id = records[0]["fields"].get("topic_id")
    print(f"[DEBUG] Topic trouvé = {topic_id}")

    return topic_id


# ---------------------------
# REMINDER PAYLOAD (Compatible Airtable)
# ---------------------------
class ReminderPayload(BaseModel):
    Client_key: str
    Admin_id: int
    Payment_link: str
    Message: str


# ---------------------------
# REMINDER ROUTE
# ---------------------------
@app.post("/reminder")
async def send_reminder(payload: ReminderPayload):
    try:
        print("🔥 ===== REMINDER TRIGGERED =====")
        print("[DEBUG] Payload brut =", payload.dict())

        client_email = payload.Client_key.lower().strip()
        admin_id = payload.Admin_id
        text = payload.Message

        print(f"[DEBUG] Email client = {client_email}")
        print(f"[DEBUG] Admin ID = {admin_id}")

        seller_slug = ADMIN_TO_SLUG.get(admin_id)
        print(f"[DEBUG] Seller slug = {seller_slug}")

        if not seller_slug:
            return {
                "status": "error",
                "error": f"Aucun seller_slug pour admin_id={admin_id}"
            }

        topic_id = find_topic_id_by_email_and_slug(client_email, seller_slug)

        if not topic_id:
            return {
                "status": "error",
                "error": f"Aucun topic trouvé pour email={client_email} et seller={seller_slug}"
            }

        staff_group_id = int(os.getenv("STAFF_GROUP_ID"))
        print(f"[DEBUG] Staff group = {staff_group_id}")

        await bot.send_message(
            chat_id=staff_group_id,
            message_thread_id=int(topic_id),
            text=text
        )

        print(f"✅ Relance envoyée dans topic {topic_id}")

        # notification admin
        await bot.send_message(
            chat_id=admin_id,
            text=f"🔔 Relance envoyée au client {client_email} (topic {topic_id})"
        )

        return {"status": "sent", "topic_id": topic_id}

    except Exception as e:
        print("❌ [REMINDER ERROR]", e)
        return {"status": "error", "error": str(e)}


# ---------------------------
# STARTUP EVENT
# ---------------------------
@app.on_event("startup")
async def startup_event():
    try:
        bott_webhook.initialize_authorized_users()
        await load_vip_topics_from_airtable()
        load_vip_topics_from_disk()
        load_annotations_from_airtable()
        await restore_missing_panels()
        asyncio.create_task(bott_webhook.scheduler_loop())
        print("[STARTUP] Système NovaPulse prêt.")

    except Exception as e:
        print(f"[STARTUP ERROR] {e}")


# ---------------------------
# CREATE CHECKOUT (PWA → BOT)
# ---------------------------
@app.post("/create-checkout")
async def create_checkout(data: dict = Body(...)):
    try:
        amount_raw = data.get("amount_cents")
        email = data.get("email")
        seller_slug = data.get("seller_slug")

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

print("🔥 >>> MAIN.PY NOVAPULSE PRÊT <<< 🔥")