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
            await bot.send_message(
                message.chat.id,
                "Merci pour ton paiement mon coeur 💕 ! Je vais t’envoyer ton contenu dans quelques secondes... Le temps de chargement !"
            )
            return

        if param == "vipaccess123":
            await bot.send_message(
                message.chat.id,
                "Bienvenue dans la communauté VIP ! Tu viens de débloquer un accès exclusif. Prépare-toi à recevoir du contenu privilégié rien que toi et moi très bientôt."
            )
            return

        # Réinitialisation du clavier
        await bot.send_message(message.chat.id, "Chargement du nouveau menu...", reply_markup=types.ReplyKeyboardRemove())

        user_name = message.from_user.first_name or "toi"
        await bot.send_message(
            message.chat.id,
            f"Salut {user_name}, que veux-tu faire ?",
            reply_markup=keyboard
        )

    # Gestion des réponses aux boutons
    @dp.message_handler(lambda message: message.text == "🔞Voir la vidéo du jour")
    async def voir_video(message: types.Message):
        await bot.send_message(
            message.chat.id,
            "Voici le lien pour acheter la vidéo du jour en toute discrétion ! 💵 Une fois payé, tu recevras directement ta vidéo dans tes messages privés 🤭 : https://app.tillypay.com/pay/ksaq9te"
        )

    @dp.message_handler(lambda message: message.text == "💭Juste discuter")
    async def juste_discuter(message: types.Message):
        await bot.send_message(
            message.chat.id,
            "Je suis là pour discuter avec toi, mais n'attends pas forcément une réponse de ma part !"
        )

    @dp.message_handler(lambda message: message.text == "✨Discuter en tant que VIP")
    async def discuter_vip(message: types.Message):
        await bot.send_message(
            message.chat.id,
            "Je t'envoie ce lien pour confirmer ton adhésion à mon VIP ! Pas d'abonnement, juste un preuve de confiance d'un montant de (1 euro 🎁) pour enfin avoir des échanges privilégiés et plus intimes avec moi...🤭https://app.tillypay.com/pay/vd4gj6j"
        )
