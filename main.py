from fastapi import FastAPI, Request
from aiogram import Bot, Dispatcher, types
import os
from dotenv import load_dotenv
from bott_webhook import register_handlers

load_dotenv()

# Initialisation
TOKEN = os.getenv('BOT_TOKEN')
bot = Bot(token=TOKEN)
dp = Dispatcher(bot=bot)

# Enregistrement des handlers personnalisés
register_handlers(dp)

# Application FastAPI
app = FastAPI()

# Route de Webhook
@app.post(f"/bot/{TOKEN}")
async def telegram_webhook(request: Request):
    data = await request.json()
    update = types.Update(**data)
    await dp.process_update(update)
    return {"ok": True}