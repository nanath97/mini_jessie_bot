from aiogram import Bot, Dispatcher, types
from aiogram.types import Update
from aiogram.dispatcher.webhook import get_new_configured_app
from aiogram.utils.executor import start_webhook
import os

# === 1. Ton token Telegram ici ===
API_TOKEN = '7623543469:AAFWp224VKWuyf32eY7SqsF6m4en3EF9nNU' # Remplace par ton vrai token Telegram

# === 2. Ton URL Render ici ===
WEBHOOK_HOST = 'https://mini-jessie-bot-1.onrender.com' # Remplace par ton URL Render
WEBHOOK_PATH = '/webhook'
WEBHOOK_URL = f"{WEBHOOK_HOST}{WEBHOOK_PATH}"

# Configuration de l'application web
WEBAPP_HOST = '0.0.0.0' # Pour Render
WEBAPP_PORT = int(os.environ.get('PORT', 3000)) # Port Render par défaut

# Création du bot
bot = Bot(token=API_TOKEN)
dp = Dispatcher(bot)

# === Tes handlers ici ===
@dp.message_handler(commands=['start'])
async def send_welcome(message: types.Message):
await message.reply("Bienvenue, ton bot fonctionne en mode Webhook !")

@dp.message_handler()
async def echo(message: types.Message):
await message.reply(f"Tu as dit : {message.text}")

# === Fonctions de démarrage/arrêt ===
async def on_startup(dispatcher):
await bot.set_webhook(WEBHOOK_URL)

async def on_shutdown(dispatcher):
await bot.delete_webhook()

# === Lancement du serveur Webhook ===
if __name__ == '__main__':
start_webhook(
dispatcher=dp,
webhook_path=WEBHOOK_PATH,
on_startup=on_startup,
on_shutdown=on_shutdown,
skip_updates=True,
host=WEBAPP_HOST,
port=WEBAPP_PORT,
)