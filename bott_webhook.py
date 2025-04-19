import os
from fastapi import FastAPI, Request
from aiogram import Bot, Dispatcher, types
from aiogram.types import Update
from dotenv import load_dotenv
import logging
import time

# === Chargement des variables d'environnement ===
load_dotenv()
TOKEN = os.getenv('BOT_TOKEN')

# === Configuration du webhook ===
WEBHOOK_PATH = f"/bot/{TOKEN}"
RENDER_WEB_SERVICE_NAME = "mini-jessie-bot"
WEBHOOK_URL = "https://" + RENDER_WEB_SERVICE_NAME + ".onrender.com" + WEBHOOK_PATH

# === Configuration du bot et de FastAPI ===
logging.basicConfig(level=logging.INFO)
bot = Bot(token=TOKEN)
Bot.set_current(bot)  # Important pour le contexte de aiogram
dp = Dispatcher(bot)
app = FastAPI()

# === Configuration du webhook au démarrage ===
@app.on_event("startup")
async def on_startup():
    webhook_info = await bot.get_webhook_info()
    if webhook_info.url != WEBHOOK_URL:
        await bot.set_webhook(url=WEBHOOK_URL)

# === Handler de test /start ===
@dp.message_handler(commands=['start'])
async def start_handler(message: types.Message):
    await message.reply("Bienvenue, ton bot fonctionne en mode Webhook !")

# === Réponse par défaut ===
@dp.message_handler()
async def echo_handler(message: types.Message):
    await message.reply(f"Tu as dit : {message.text}")

# === Route webhook pour Telegram ===
@app.post(WEBHOOK_PATH)
async def process_webhook(update: dict, request: Request):
    telegram_update = Update(**update)
    await dp.process_update(telegram_update)
    return {"ok": True}
