from fastapi import FastAPI, Request
from aiogram import Bot, Dispatcher, types
import os
from dotenv import load_dotenv

load_dotenv()

from core import bot, dp  # ✅ à importer après load_dotenv
from stripe_webhook import router as stripe_router  # ✅ après load_dotenv

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
        import bott_webhook  # ✅ import ici, pas tout en haut du fichier
        bott_webhook.initialize_authorized_users()
        print(f"[STARTUP] Initialisation des utilisateurs VIP terminée.")
    except Exception as e:
        print(f"[STARTUP ERROR] Erreur pendant le chargement des VIP : {e}")

# ✅ Route Stripe (doit être incluse après tout le reste)
app.include_router(stripe_router)

print("🔥 >>> FICHIER MAIN.PY BIEN LANCÉ <<< 🔥")
