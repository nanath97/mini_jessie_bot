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
Bot.set_current(bot)
dp = Dispatcher(bot)
app = FastAPI()

# === Configuration du webhook au démarrage ===
@app.on_event("startup")
async def on_startup():
    webhook_info = await bot.get_webhook_info()
    if webhook_info.url != WEBHOOK_URL:
        await bot.set_webhook(url=WEBHOOK_URL)

# === Commande /start avec les boutons ===
@dp.message_handler(commands=['start'])
async def send_welcome(message: types.Message):
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
    buttons = ["Discuter en tant que VIP", "Voir le contenu du jour", "Juste discuter"]
    keyboard.add(*buttons)

    await message.answer("Salut mon coeur ! Que veux-tu faire ?", reply_markup=keyboard)

# === Réponse pour chaque bouton ===

@dp.message_handler(lambda message: message.text == "Discuter en tant que VIP")
async def show_preview(message: types.Message):
    await message.answer("Nous allons faire connaissance, je t'offrirai des cadeaux surprises et je vais te montrer mon corps sous toutes ses formes! Tu pourras les débloquer après achat. Clique ici : https://t.me/+Kk86-FYp4S05OWQ0")

@dp.message_handler(lambda message: message.text == "Voir le contenu du jour")
async def offer(message: types.Message):
    await message.answer("Aujourd’hui, tu peux débloquer 1 vidéo de moi me doigtant comme une coquine dans ma salle de bain, plus 1 figurine digitale de ma miniature pour seulement 39€. Offre valable pendant 1 heure. Clique ici :https://t.me/+8Chmd4e9zVRjZjVk")

@dp.message_handler(lambda message: message.text == "Juste discuter")
async def chat(message: types.Message):
    await message.answer("Tu peux m’écrire ici directement. Mais sache que mes contenus exclusifs sont réservés aux abonnés ! Et ce n'est pas sûr que je te réponde de suite...")

# === Route webhook pour Telegram ===
@app.post(WEBHOOK_PATH)
async def process_webhook(update: dict, request: Request):
    telegram_update = Update(**update)
    await dp.process_update(telegram_update)
    return {"ok": True}
