from fastapi import FastAPI, Request
from aiogram import types
import os
from dotenv import load_dotenv

load_dotenv()

# ⚠️ IMPORTER core AVANT bott_webhook
from core import bot, dp, storage
import bott_webhook  # surtout après dp/storage
from stripe_webhook import router as stripe_router

app = FastAPI()

@app.post(f"/bot/{os.getenv('BOT_TOKEN')}")
async def telegram_webhook(request: Request):
    try:
        data = await request.json()
        update = types.Update(**data)
        await dp.process_update(update)
    except Exception as e:
        print("Erreur dans webhook :", e)
        return {"ok": False, "error": str(e)}
    return {"ok": True}

@app.on_event("startup")
async def startup_event():
    try:
        bott_webhook.initialize_authorized_users()
        print(f"[STARTUP] Initialisation des utilisateurs VIP terminée.")
    except Exception as e:
        print(f"[STARTUP ERROR] Erreur pendant le chargement des VIP : {e}")

app.include_router(stripe_router)

print("🔥 >>> FICHIER MAIN.PY BIEN LANCÉ <<< 🔥")
