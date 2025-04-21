from aiogram import types
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from aiogram.dispatcher import Dispatcher
from fastapi import FastAPI

app = FastAPI()

# Clavier sans emojis
keyboard = ReplyKeyboardMarkup(resize_keyboard=True)
keyboard.add(
    KeyboardButton("Voir le contenu du jour"),
    KeyboardButton("Juste discuter"),
    KeyboardButton("Discuter en tant que VIP")
)

# Handlers
def register_handlers(dp: Dispatcher):
    @dp.message_handler(commands=['start'])
    async def send_welcome(message: types.Message):
        param = message.get_args()

        if param == "paid123":
            await message.answer("Merci pour ton paiement ! Je vais t’envoyer ton contenu très bientôt.")
            return

        user_name = message.from_user.first_name
        await message.answer(f"Salut {user_name}, que veux-tu faire ?", reply_markup=keyboard)

    @dp.message_handler(lambda message: message.text == "Voir le contenu du jour")
    async def handle_contenu(message: types.Message):
        await message.answer("Voici le contenu du jour spécialement pour toi.")

    @dp.message_handler(lambda message: message.text == "Juste discuter")
    async def handle_discussion(message: types.Message):
        await message.answer("Je suis là pour discuter avec toi, pose-moi toutes tes questions !")

    @dp.message_handler(lambda message: message.text == "Discuter en tant que VIP")
    async def handle_vip(message: types.Message):
        await message.answer("Bienvenue dans l’espace VIP, tu peux me poser tes demandes les plus exclusives.")