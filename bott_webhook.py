from core import bot, dp
from aiogram import types
import requests
from datetime import datetime

# Clés API Airtable
AIRTABLE_API_KEY = "patAGB8w2HG44dvJy.8b57a2fe014dfcabc109214abf6c78aa2784b9701b6768ba40df7b32ab5df285"
BASE_ID = "appdA5tvdjXiktFzq"
TABLE_NAME = "Client Telegram"

# Liste des prix autorisés
prix_list = [9, 14, 19, 24, 29, 34, 39, 44, 49, 59, 69, 79, 89, 99]

# Liste blanche des liens autorisés
WHITELIST_LINKS = [
    "https://novapulseonline.wixsite.com/",
    "https://buy.stripe.com/",
]

# Création du clavier principal
keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
keyboard.add(
    types.KeyboardButton("🔞Voir la vidéo du jour"),
    types.KeyboardButton("👀Je suis un voyeur"),
    types.KeyboardButton("✨Discuter en tant que VIP")
)

# Utilisateurs validés
declaring_utilisateurs_valides = set()

# Fonction d'envoi Airtable
def log_to_airtable(pseudo, user_id, type_acces, montant, contenu, email):
    url = f"https://api.airtable.com/v0/{BASE_ID}/{TABLE_NAME}"
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
    requests.post(url, json=data, headers=headers)

# Fonction de détection de lien non autorisé
def lien_non_autorise(text):
    return any(
        part.startswith(("http", "https"))and not any(allowed in part for allowed in WHITELIST_LINKS)
        for part in text.split()
    )

# Commande /start
@dp.message_handler(commands=['start'])
async def handle_start(message: types.Message):
    param = message.get_args()

    if param.startswith("paid") and param[4:].isdigit():
        montant = int(param[4:])
        if montant in prix_list:
            await bot.send_message(
                message.chat.id,
                f"Merci pour ton paiement de {montant}€ 💖"
            )
            declaring_utilisateurs_valides.add(message.from_user.id)
            log_to_airtable(
                message.from_user.username,
                message.from_user.id,
                "Achat direct",
                montant,
                "Vidéo privée",
                "email@exemple.com"
            )
            return

    await bot.send_message(
        message.chat.id,
        f"Salut {message.from_user.first_name or 'toi'}, que veux-tu faire ?",
        reply_markup=keyboard
    )

# Gestion des boutons
@dp.message_handler(lambda message: message.text == "🔞Voir la vidéo du jour")
async def voir_video(message: types.Message):
    declaring_utilisateurs_valides.add(message.from_user.id)
    await bot.send_message(
        message.chat.id,
        "Voici la vidéo du jour 🔥!"
    )

@dp.message_handler(lambda message: message.text == "✨Discuter en tant que VIP")
async def discuter_vip(message: types.Message):
    declaring_utilisateurs_valides.add(message.from_user.id)
    await bot.send_message(
        message.chat.id,
        "Bienvenue dans la discussion VIP ✨!"
    )

@dp.message_handler(lambda message: message.text == "👀Je suis un voyeur")
async def voyeur(message: types.Message):
    declaring_utilisateurs_valides.add(message.from_user.id)
    keyboard_confirmation = types.ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard_confirmation.add(
        types.KeyboardButton("✅ Oui je confirme"),
        types.KeyboardButton("🚀 Non je veux rejoindre le VIP")
    )
    await bot.send_message(
        message.chat.id,
        "Confirme si tu veux rester ou rejoindre le VIP.",
        reply_markup=keyboard_confirmation
    )

@dp.message_handler(lambda message: message.text == "✅ Oui je confirme")
async def confirmer_voyeur(message: types.Message):
    await bot.send_message(
        message.chat.id,
        "Tu as choisi de rester un simple spectateur. Accès limité."
    )

@dp.message_handler(lambda message: message.text == "🚀 Non je veux rejoindre le VIP")
async def rejoindre_vip(message: types.Message):
    await bot.send_message(
        message.chat.id,
        "Parfait ! Voici le lien pour rejoindre le VIP : https://buy.stripe.com/4gwg32fhF4K62fCdQR",
        reply_markup=keyboard
    )

# Suppression des liens non whitelistés
@dp.message_handler(lambda message: ("http" in message.text or "https" in message.text) and message.from_user.id in declaring_utilisateurs_valides)
async def detecter_lien_externe(message: types.Message):
    if lien_non_autorise(message.text):
        try:
            await bot.delete_message(chat_id=message.chat.id, message_id=message.message_id)
            await bot.send_message(
                chat_id=message.chat.id,
                text="🛘 Les liens extérieurs ne sont pas autorisés."
            )
        except Exception as e:
            print("Erreur suppression lien externe :", e)

# Chat libre après validation
@dp.message_handler(lambda message: message.from_user.id in declaring_utilisateurs_valides)
async def chat_libre(message: types.Message):
    print(f"📨 Nouveau message reçu de {message.from_user.username} : {message.text}")
    # Pas de réponse automatique ici

