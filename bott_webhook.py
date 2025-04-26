from core import bot, dp
from aiogram import types
import requests
import asyncio
from datetime import datetime

# === CONFIGURATION ===
ADMIN_ID = 7334072965  # Ton ID Telegram Admin
AIRTABLE_API_KEY = "patAGB8w2HG44dvJy.8b57a2fe014dfcabc109214ab5f6c78aa2784b9701b6768ba40df7b32ab5df285"
BASE_ID = "appdA5tvdjXiktFzq"
TABLE_NAME = "Client Telegram"

# === CLAVIER PRINCIPAL ===
keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
keyboard.add(
    types.KeyboardButton("🔞Voir la vidéo du jour"),
    types.KeyboardButton("👀Je suis un voyeur"),
    types.KeyboardButton("✨Discuter en tant que VIP")
)

# === ENREGISTRER UN EVENEMENT DANS AIRTABLE ===
async def log_to_airtable(pseudo, user_id, type_acces, montant, contenu, email):
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
        await asyncio.to_thread(requests.post, url, json=data, headers=headers)
    except Exception as e:
        print(f"Erreur Airtable : {e}")

# === BLOQUER LIENS NON WHITELISTÉS ===
@dp.message_handler(lambda message: (message.text or message.caption) and "http" in (message.text or message.caption))
async def detect_external_links(message: types.Message):
    WHITELIST_LINKS = [
        "https://novapulseonline.wixsite.com/",
        "https://buy.stripe.com/"
    ]
    content = message.text if message.text else message.caption
    if not any(allowed in content for allowed in WHITELIST_LINKS):
        try:
            await bot.delete_message(message.chat.id, message.message_id)
            await bot.send_message(message.chat.id, "🚫 Les liens extérieurs ne sont pas autorisés.")
            print(f"🔴 Message avec lien interdit supprimé : {content}")
        except Exception as e:
            print(f"Erreur suppression lien : {e}")

# === /START POUR PAIEMENT & VIP ===
@dp.message_handler(commands=["start"])
async def handle_start(message: types.Message):
    param = message.get_args()
    prix_list = [9, 14, 19, 24, 29, 34, 39, 44, 49, 59, 69, 79, 89, 99]

    if param.startswith("paid") and param[4:].isdigit():
        montant = int(param[4:])
        if montant in prix_list:
            await bot.send_message(message.chat.id, f"✅ Merci pour ton paiement de {montant}€ 💖")
            await bot.send_message(ADMIN_ID, f"💰 Nouveau paiement de {montant}€ de {message.from_user.username or message.from_user.first_name}.")
            await log_to_airtable(message.from_user.username or "", message.from_user.id, "Achat direct", float(montant), "Vidéo privée", "vinteo.ac@gmail.com")
            return

    if param in ["vipaccess", "vipaccess123"]:
        await bot.send_message(message.chat.id, "✨ Bienvenue dans le VIP !")
        await bot.send_message(ADMIN_ID, f"🌟 Nouveau VIP : {message.from_user.username or message.from_user.first_name}.")
        await log_to_airtable(message.from_user.username or "", message.from_user.id, "VIP", 1.00, "Accès VIP", "vinteo.ac@gmail.com")
        return

    await bot.send_message(message.chat.id, f"👋 Salut {message.from_user.first_name or 'toi'}, que veux-tu faire ?", reply_markup=keyboard)

# === GESTION DES BOUTONS ===
@dp.message_handler(lambda message: message.text == "🔞Voir la vidéo du jour")
async def voir_video(message: types.Message):
    await bot.send_message(message.chat.id, "🎥 Voici ta vidéo du jour : https://buy.stripe.com/fZeg328Th4K67zW9AA")

@dp.message_handler(lambda message: message.text == "✨Discuter en tant que VIP")
async def discuter_vip(message: types.Message):
    await bot.send_message(message.chat.id, "🚀 Rejoins le VIP ici : https://buy.stripe.com/4gwg32fhF4K62fCdQR")

@dp.message_handler(lambda message: message.text == "👀Je suis un voyeur")
async def je_suis_voyeur(message: types.Message):
    keyboard_confirm = types.ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard_confirm.add(
        types.KeyboardButton("✅ Oui je confirme (bannir)"),
        types.KeyboardButton("🚀 Non, je veux rejoindre le VIP")
    )
    await bot.send_message(message.chat.id, "Confirme ton choix :", reply_markup=keyboard_confirm)

@dp.message_handler(lambda message: message.text == "✅ Oui je confirme (bannir)")
async def confirmer_voyeur(message: types.Message):
    await bot.send_message(message.chat.id, "🛑 Tu restes simple spectateur.")

@dp.message_handler(lambda message: message.text == "🚀 Non, je veux rejoindre le VIP")
async def rejoindre_vip(message: types.Message):
    await bot.send_message(message.chat.id, "🚀 Super ! Voici ton lien VIP : https://buy.stripe.com/4gwg32fhF4K62fCdQR", reply_markup=keyboard)

# === RELAY CLIENT ➔ ADMIN (TOUT TYPE) ===
@dp.message_handler(lambda message: message.from_user.id != ADMIN_ID)
async def relay_all_from_client(message: types.Message):
    try:
        await bot.forward_message(chat_id=ADMIN_ID, from_chat_id=message.chat.id, message_id=message.message_id)
    except Exception as e:
        print(f"Erreur relay client ➔ admin : {e}")

# === RELAY ADMIN ➔ CLIENT ===
@dp.message_handler(lambda message: message.from_user.id == ADMIN_ID)
async def relay_all_from_admin(message: types.Message):
    if message.reply_to_message and message.reply_to_message.forward_from:
        target_id = message.reply_to_message.forward_from.id
        try:
            await bot.copy_message(chat_id=target_id, from_chat_id=message.chat.id, message_id=message.message_id)
        except Exception as e:
            await bot.send_message(chat_id=ADMIN_ID, text="❗Erreur pour envoyer au client.")
    else:
        await bot.send_message(chat_id=ADMIN_ID, text="❗Merci de répondre à un message transféré.")
