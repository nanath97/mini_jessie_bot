from aiogram import types
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from aiogram.dispatcher import Dispatcher

# Clavier sans emojis
keyboard = ReplyKeyboardMarkup(resize_keyboard=True)
keyboard.add(
    KeyboardButton("🔞Voir la vidéo du jour"),
    KeyboardButton("💭Juste discuter"),
    KeyboardButton("✨Discuter en tant que VIP")
)

# Enregistrement des handlers avec bot explicite
def register_handlers(bot, dp: Dispatcher):
    @dp.message_handler(commands=['start'])
    async def handle_start(message: types.Message):
        param = message.get_args()

        if param == "paid123":
            await bot.send_message(message.chat.id, "Merci pour ton paiement mon coeur 💕 ! Je vais t’envoyer ton contenu dans quelques secondes... Le temps de chargement !")
            return

        # Réinitialisation du clavier
        await bot.send_message(message.chat.id, "Chargement du nouveau menu...", reply_markup=types.ReplyKeyboardRemove())

        user_name = message.from_user.first_name
        await bot.send_message(message.chat.id, f"Salut {user_name}, que veux-tu faire ?", reply_markup=keyboard)

    @dp.message_handler(lambda message: message.text == "🔞Voir la vidéo du jour")
    async def handle_content(message: types.Message):
        await bot.send_message(message.chat.id, "Voici le lien pour acheter la vidéo du jour en toute discrétion ! 🪙Une fois payé; tu recevras directement ta vidéo dans tes messages privés 🤭 : https://app.tillypay.com/pay/ksaq9te")

    @dp.message_handler(lambda message: message.text == "💭Juste discuter")
    async def handle_chat(message: types.Message):
        await bot.send_message(message.chat.id, "Je suis là pour discuter avec toi, mais n'attends pas forcément une réponse de ma part !")

    @dp.message_handler(lambda message: message.text == "✨Discuter en tant que VIP")
    async def handle_vip(message: types.Message):
        await bot.send_message(message.chat.id, "Je t'enverrai un message en privé pour faire connaissance, et échanger sur nos fantasmes les plus fous après paiement bien-sûr 🔞🎁🤭 ! Voici le lien vers le groupe VIP : https://t.me/+Kk86-FYp4S05OWQ0")