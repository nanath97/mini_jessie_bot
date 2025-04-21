from aiogram import types
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from aiogram.dispatcher import Dispatcher

# Clavier sans emojis
keyboard = ReplyKeyboardMarkup(resize_keyboard=True)
keyboard.add(
    KeyboardButton("Voir le contenu du jour"),
    KeyboardButton("Juste discuter"),
    KeyboardButton("Discuter en tant que VIP")
)

# Enregistrement des handlers
def register_handlers(dp: Dispatcher):
    @dp.message_handler(commands=['start'])
    async def handle_start(message: types.Message):
        param = message.get_args()

        # Cas paiement TillyPay
        if param == "paid123":
            await message.answer("Merci pour ton paiement ! Je vais t’envoyer ton contenu très bientôt.")
            return

        # Réinitialisation propre : d’abord un message sans clavier pour supprimer les anciens
        await message.answer("Chargement du nouveau menu...", reply_markup=types.ReplyKeyboardRemove())
        
        # Puis envoi du message avec le clavier à jour
        user_name = message.from_user.first_name
        await message.answer(f"Salut {user_name}, que veux-tu faire ?", reply_markup=keyboard)

    @dp.message_handler(lambda message: message.text == "Voir le contenu du jour")
    async def handle_content(message: types.Message):
        await message.answer("Voici le lien vers le groupe pour acheter le contenu : https://t.me/ton_groupe_achat")

    @dp.message_handler(lambda message: message.text == "Juste discuter")
    async def handle_chat(message: types.Message):
        await message.answer("Je suis là pour discuter avec toi, pose-moi toutes tes questions !")

    @dp.message_handler(lambda message: message.text == "Discuter en tant que VIP")
    async def handle_vip(message: types.Message):
        await message.answer("Voici le lien vers le groupe VIP : https://t.me/ton_groupe_vip")