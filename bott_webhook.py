
from dotenv import load_dotenv
load_dotenv()

import os
from aiogram import Bot, Dispatcher, types
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from aiogram.utils import executor
from fastapi import FastAPI
import logging

BOT_TOKEN = os.getenv("BOT_TOKEN")

# Configure logging
logging.basicConfig(level=logging.INFO)

# Initialize bot and dispatcher
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(bot)

# FastAPI app (for Render webhook)
app = FastAPI()

# === Commande /start avec les boutons personnalisés ===
@dp.message_handler(commands=['start'])
async def handle_start(message: types.Message):
    payload = message.get_args()
    user_name = message.from_user.first_name or message.from_user.username

    if payload == "paid123":
        await bot.send_message(
            chat_id=message.from_user.id,
            text="Merci mon cœur pour ton achat 😇 ! Ta vidéo est en cours de chargement, elle arrive dans un instant, ne t'inquiète pas mon cœur 💗"
        )
    elif payload == "vipaccess":
        await bot.send_message(
            chat_id=message.from_user.id,
            text=f"Coucou {user_name} ! Ça me fait plaisir que tu veuilles apprendre à me connaître plus en profondeur 🤭💦"
        )
    else:
        keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
        buttons = [
            "Discuter en tant que VIP",
            "Voir le contenu du jour",
            "Juste discuter"
        ]
        keyboard.add(*buttons)
        await message.answer(f"Salut {user_name} ! Que veux-tu faire ?", reply_markup=keyboard)

# === Réponses pour chaque bouton ===
@dp.message_handler(lambda message: message.text == "🔥 Discuter en tant que VIP")
async def show_preview(message: types.Message):
    await message.answer("Nous allons faire connaissance, discuter de tout et de rien et je t’offrirai des moments privilégiés réservés aux VIP après achat.")

@dp.message_handler(lambda message: message.text == "📸 Voir le contenu du jour")
async def show_content(message: types.Message):
    await message.answer("Voici ma vidéo super sex disponible aujourd’hui. Clique ici pour en profiter !")

@dp.message_handler(lambda message: message.text == "💬 Juste discuter")
async def just_chat(message: types.Message):
    await message.answer("Désolée; mais si c'est juste pour discuter et rien de plus, je ne pourrais pas te répondre...J'en suis vraiment désolée !")
