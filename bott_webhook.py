
from core import bot, dp
from aiogram import types
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from datetime import datetime
import requests

# Configuration Airtable
AIRTABLE_API_KEY = "patAGB8w2HG44dvJy.8b57a2fe014dfcabc109214abf6c78aa2784b9701b6768ba40df7b32ab5df285"
BASE_ID = "appdA5tvdjXiktFzq"
TABLE_NAME = "Client Telegram"

def log_to_airtable(pseudo, user_id, type_acces, montant, contenu, email):
    url = f"https://api.airtable.com/v0/{BASE_ID}/{TABLE_NAME.replace(' ', '%20')}"
    headers = {
        "Authorization": f"Bearer {AIRTABLE_API_KEY}",
        "Content-Type": "application/json"
    }
    data = {
        "fields": {
            "Pseudo Telegram": pseudo,
            "ID Telegram": str(user_id),
            "Type acces": type_acces,
            "Montant": montant,
            "Contenu": contenu,
            "Email": email,
            "Date": datetime.now().isoformat()
        }
    }
    try:
        response = requests.post(url, json=data, headers=headers)
        print("Airtable response:", response.status_code, response.text)
        return response.status_code, response.text
    except Exception as e:
        print("Erreur lors de l’envoi à Airtable :", e)
        return None, str(e)

# Initialisation des utilisateurs validés
utilisateurs_valides = set()

# Boutons autorisés
BOUTONS_AUTORISES = [
    "🔞Voir la vidéo du jour",
    "👀Je suis un voyeur",
    "✨Discuter en tant que VIP",
    "✅ Oui, je confirme (bannir)",
    "🚀 Non, je veux rejoindre le VIP"
]

# Clavier
keyboard = ReplyKeyboardMarkup(resize_keyboard=True)
keyboard.add(
    KeyboardButton("🔞Voir la vidéo du jour"),
    KeyboardButton("👀Je suis un voyeur"),
    KeyboardButton("✨Discuter en tant que VIP")
)

# Commande start
@dp.message_handler(commands=["start"])
async def handle_start(message: types.Message):
    param = message.get_args()
    email = "vinteo@gmail.com"
    prix_list = [9, 14, 19, 24, 29, 34, 39, 44, 49, 59, 69, 79, 89, 99]

    if param.startswith("paid") and param[4:].isdigit():
        montant = int(param[4:])
        if montant in prix_list:
            await bot.send_message(
                message.chat.id,
                f"Merci pour ton paiement 💕"
            )
            utilisateurs_valides.add(message.from_user.id)
            log_to_airtable(
                pseudo=message.from_user.username,
                user_id=message.from_user.id,
                type_acces="Achat direct",
                montant=montant,
                contenu="Vidéo privée",
                email=email
            )
            return

    if param == "vipaccess123":
        await bot.send_message(
            message.chat.id,
            "Tu fais maintenant partie de la communauté VIP ✨ !"
        )
        utilisateurs_valides.add(message.from_user.id)
        log_to_airtable(
            pseudo=message.from_user.username,
            user_id=message.from_user.id,
            type_acces="VIP",
            montant=1.00,
            contenu="Accès communauté VIP",
            email=email
        )
        return

    user_name = message.from_user.first_name or "toi"
    await bot.send_message(
        message.chat.id,
        f"Salut {user_name}, que veux-tu faire ?",
        reply_markup=keyboard
    )

# Handlers boutons
@dp.message_handler(lambda message: message.text == "🔞Voir la vidéo du jour")
async def voir_video(message: types.Message):
    utilisateurs_valides.add(message.from_user.id)
    await bot.send_message(
        message.chat.id,
        "Voici le lien pour acheter la vidéo du jour : https://buy.stripe.com/fZeg328Th4K67zW9AA"
    )

@dp.message_handler(lambda message: message.text == "✨Discuter en tant que VIP")
async def discuter_vip(message: types.Message):
    utilisateurs_valides.add(message.from_user.id)
    await bot.send_message(
        message.chat.id,
        "Lien VIP : https://buy.stripe.com/4gwg32fhF4K62fCdQR"
    )

@dp.message_handler(lambda message: message.text == "👀Je suis un voyeur")
async def confirmer_voyeur(message: types.Message):
    clavier_confirmation = ReplyKeyboardMarkup(resize_keyboard=True)
    clavier_confirmation.add(
        KeyboardButton("✅ Oui, je confirme (bannir)"),
        KeyboardButton("🚀 Non, je veux rejoindre le VIP")
    )
    await bot.send_message(
        message.chat.id,
        "Tu veux quitter l'expérience ?",
        reply_markup=clavier_confirmation
    )

@dp.message_handler(lambda message: message.text == "✅ Oui, je confirme (bannir)")
async def bannir_utilisateur(message: types.Message):
    await bot.send_message(
        message.chat.id,
        "C’est noté, tu ne feras plus partie de cette expérience."
    )

@dp.message_handler(lambda message: message.text == "🚀 Non, je veux rejoindre le VIP")
async def rediriger_vers_vip(message: types.Message):
    utilisateurs_valides.add(message.from_user.id)
    await bot.send_message(
        message.chat.id,
        "Voici ton lien VIP : https://buy.stripe.com/4gwg32fhF4K62fCdQR"
    )

# Blocage messages libres non validés
@dp.message_handler(lambda message:
    message.text and
    not message.text.startswith("/start") and
    message.text not in BOUTONS_AUTORISES and
    message.from_user.id not in utilisateurs_valides
)
async def bloquer_saisie_libre(message: types.Message):
    try:
        await bot.delete_message(chat_id=message.chat.id, message_id=message.message_id)
        await bot.send_message(
            chat_id=message.chat.id,
            text="🛑 Merci de cliquer sur un des boutons ci-dessous pour continuer."
        )
        print(f"🛑 Message bloqué pour utilisateur non validé : {message.from_user.username}")
    except Exception as e:
        print("Erreur suppression message libre :", e)

# Gestion du chat libre (seulement utilisateurs validés)
@dp.message_handler(lambda message: message.from_user.id in utilisateurs_valides)
async def chat_libre(message: types.Message):
    print(f"Message libre reçu de {message.from_user.username}: {message.text}")
    # Tu peux ici aussi transférer vers ton compte admin ou loguer ailleurs
