from fastapi import FastAPI, Request
from aiogram import Bot, Dispatcher, types
import os
from dotenv import load_dotenv
from core import bot, dp
import bott_webhook
from stripe_webhook import router as stripe_router





load_dotenv()


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
        import bott_webhook
        bott_webhook.initialize_authorized_users()
        print(f"[STARTUP] Initialisation des utilisateurs VIP terminée.")
    except Exception as e:
        print(f"[STARTUP ERROR] Erreur pendant le chargement des VIP : {e}")

# === 221097 DEBUT
app.include_router(stripe_router)
# === 221097 FIN

@app.post("/stripe/webhook")
async def stripe_webhook_direct(request: Request):
    print("📥 Webhook Stripe reçu directement dans main.py")
    return {"status": "ok"}
# === 221097 FINV1