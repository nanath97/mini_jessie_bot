
from aiogram import Bot, Dispatcher, types
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from aiogram.utils import executor
from fastapi import FastAPI
import logging

BOT_TOKEN = "YOUR_BOT_TOKEN"

# Configure logging
logging.basicConfig(level=logging.INFO)

# Initialize bot and dispatcher
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(bot)

# FastAPI app (for Render webhook)
app = FastAPI()

@dp.message_handler(commands=['start'])
async def start_command(message: types.Message):
    payload = message.get_args()
    user_full_name = message.from_user.first_name

    if payload == "paid123":
        await message.answer("Merci mon cœur pour ton achat 😇 ! Ta vidéo est en cours de chargement, elle arrive dans un instant, ne t’inquiète pas mon cœur 💗")
    elif payload == "vipaccess":
        await message.answer(f"Coucou {user_full_name} ! Ça me fait plaisir que tu veuilles apprendre à me connaître plus en profondeur 🤭💦")
    else:
        buttons = ReplyKeyboardMarkup(resize_keyboard=True)
        buttons.add(KeyboardButton("Discuter en tant que VIP 🔥"))
        buttons.add(KeyboardButton("Voir le contenu du jour 📸"))
        buttons.add(KeyboardButton("Juste discuter 💬"))
        await message.answer(f"Hello, {user_full_name} !", reply_markup=buttons)

# Le reste de ton code webhook + handlers Telegram ici...
