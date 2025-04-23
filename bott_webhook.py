from aiogram import types
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from aiogram.dispatcher import Dispatcher
import requests
from datetime import datetime

# --- CONFIGURATION AIRTABLE ---
AIRTABLE_API_KEY = "patPeZWTWqRxXZs9Y.7c7e244d42e71d3556943f17cfab41410ac4d7a9224a302ae10d375cd9fb25d1"
BASE_ID = "appdA5tvdjXiktFzq"
TABLE_NAME = "Clients Telegram"

def log_to_airtable(pseudo, user_id, type_acces, montant, contenu):
    url = f"https://api.airtable.com/v0/{BASE_ID}/{TABLE_NAME.replace(' ', '%20')}"
    headers = {
        "Authorization": f"Bearer {AIRTABLE_API_KEY}",
        "Content-Type": "application/json"
    }
    data = {
        "fields": {
            "Pseudo Telegram": pseudo,
            "ID Telegram": str(user_id),
            "Type d'accès": type_acces,
            "Date du paiement": datetime.now().isoformat(),
            "Montant (€)": montant,
            "Contenu acheté": contenu
        }
    }
    response = requests.post(url, json=data, headers=headers)
    return response.status_code, response.text

# Clavier avec emojis
keyboard = ReplyKeyboardMarkup(resize_keyboard=True)
keyboard.add(
    KeyboardButton("🔞Voir la vidéo du jour"),
    KeyboardButton("👀Je suis un voyeur"),
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
            log_to_airtable(
                pseudo=message.from_user.username,
                user_id=message.from_user.id,
                type_acces="Achat direct",
                montant=39.00,
                contenu="Vidéo privée"
            )
            return

        if param == "vipaccess123":
            await bot.send_message(
                message.chat.id,
                "Bienvenue dans la communauté VIP ! Tu viens de débloquer un accès exclusif. Prépare-toi à recevoir du contenu privilégié très bientôt."
            )
            log_to_airtable(
                pseudo=message.from_user.username,
                user_id=message.from_user.id,
                type_acces="VIP",
                montant=1.00,
                contenu="Accès communauté VIP"
            )
            return

        
        # Gestion des paiements standards prédéfinis
        prix_list = [9, 14, 19, 25, 29, 34, 39, 45, 49, 59, 69, 79, 89, 99]
        if param.startswith("paid") and param[4:].isdigit():
            montant = int(param[4:])
            if montant in prix_list:
                await bot.send_message(
                    message.chat.id,
                    f"Merci pour ton paiement 💕"
                )
                log_to_airtable(
                    pseudo=message.from_user.username,
                    user_id=message.from_user.id,
                    type_acces="Achat direct",
                    montant=montant,
                    contenu=f"Contenu payé de {montant} €"
                )
                return
    
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
            "Voici le lien pour acheter la vidéo du jour en toute discrétion ! 💵 Une fois payé, tu recevras directement ta vidéo ici dans notre conversation 🤭 : https://app.tillypay.com/pay/ksaq9te"
        )

    @dp.message_handler(lambda message: message.text == "✨Discuter en tant que VIP")
    async def discuter_vip(message: types.Message):
        await bot.send_message(
            message.chat.id,
            "Je t'envoie ce lien pour confirmer ton adhésion à mon VIP ! Pas d'abonnement, juste un preuve de confiance d'un montant de (1 euro 🎁) pour enfin avoir des échanges privilégiés et plus intimes avec moi...🤭https://app.tillypay.com/pay/vd4gj6j"
        )

    @dp.message_handler(lambda message: message.text == "👀Je suis un voyeur")
    async def confirmer_voyeur(message: types.Message):
        clavier_confirmation = ReplyKeyboardMarkup(resize_keyboard=True)
        clavier_confirmation.add(
        KeyboardButton("✅ Oui, je confirme (bannir)"),
        KeyboardButton("🚀 Non, je veux rejoindre le VIP")
    )
        await bot.send_message(
        message.from_user.id,
        "Tu t'apprêtes à quitter mon canal privé. Si tu confirmes, tu ne recevras plus rien 🥹.",
        reply_markup=clavier_confirmation
    )
    @dp.message_handler(lambda message: message.text == "✅ Oui, je confirme (bannir)")
    async def bannir_utilisateur(message: types.Message):
        log_to_airtable(
            pseudo=message.from_user.username,
            user_id=message.from_user.id,
            type_acces="blacklisté",
            montant=0,
            contenu="Refus explicite"
        )
        await bot.send_message(
            message.from_user.id,
            "C’est noté ! Tu ne feras plus partie de cette expérience. Bonne route."
        )

    @dp.message_handler(lambda message: message.text == "🚀 Non, je veux rejoindre le VIP")
    async def rediriger_vers_vip(message: types.Message):
        await bot.send_message(
            message.from_user.id,
            "Parfait. Voici le lien pour rejoindre le groupe VIP (1€) : https://app.tillypay.com/pay/vd4gj6j"
        )
