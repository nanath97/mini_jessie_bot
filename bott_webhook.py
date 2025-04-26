from core import bot, dp
from aiogram import types
import os
from datetime import datetime
from aiogram.dispatcher.handler import CancelHandler
import requests

# --- CONFIGURATION AIRTABLE ---
AIRTABLE_API_KEY = "patAGB8w2HG44dvJy.8b57a2fe014dfcabc109214abf6c78aa2784b9701b6768ba40df7b32ab5df285"
BASE_ID = "appdA5tvdjXiktFzq"
TABLE_NAME = "Client Telegram"

# ADMIN ID
ADMIN_ID = 7334072965

# Liste des prix autorisés
prix_list = [9, 14, 19, 24, 29, 34, 39, 44, 49, 59, 69, 79, 89, 99]

# Liste blanche des liens autorisés
WHITELIST_LINKS = [
    "https://novapulseonline.wixsite.com/",
    "https://buy.stripe.com/",
    "https://t.me/mini_jessie_bot?start=paid"
]

# Fonction de détection de lien non autorisé
def lien_non_autorise(text):
    links = [part for part in text.split() if part.startswith("http")]
    for link in links:
        if not any(allowed in link for allowed in WHITELIST_LINKS):
            return True
    return False

# Fonction pour ajouter un paiement à Airtable
def enregistrer_paiement_airtable(username, user_id, montant, type_paiement):
    url = f"https://api.airtable.com/v0/{BASE_ID}/{TABLE_NAME}"
    headers = {
        "Authorization": f"Bearer {AIRTABLE_API_KEY}",
        "Content-Type": "application/json"
    }
    data = {
        "fields": {
            "username": username or "-",
            "user_id": str(user_id),
            "montant": str(montant),
            "type": type_paiement,
            "date": datetime.now().strftime("%d/%m/%Y %H:%M")
        }
    }
    response = requests.post(url, json=data, headers=headers)
    if response.status_code != 200:
        print(f"Erreur Airtable: {response.text}")

# Création du clavier
keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
keyboard.add(
    types.KeyboardButton("🔞Voir la vidéo du jour"),
    types.KeyboardButton("👀Je suis un voyeur"),
    types.KeyboardButton("✨Discuter en tant que VIP")
)

# Commande /start
@dp.message_handler(commands=["start"])
async def handle_start(message: types.Message):
    param = message.get_args()

    if param.startswith("paid") and param[4:].isdigit():
        montant = int(param[4:])
        if montant in prix_list:
            await bot.send_message(message.chat.id, f"✅ Merci pour ton paiement de {montant}€ 💖")
            await bot.send_message(ADMIN_ID, f"💰 Nouveau paiement de {montant}€ de {message.from_user.username or message.from_user.first_name}.")
            enregistrer_paiement_airtable(message.from_user.username or message.from_user.first_name, message.from_user.id, montant, "Paiement standard")
            await bot.send_message(ADMIN_ID, "✅ Paiement enregistré dans Airtable.")
            return

    if param in ["vipaccess", "vipaccess123"]:
        await bot.send_message(message.chat.id, "✨ Bienvenue dans le VIP !")
        await bot.send_message(ADMIN_ID, f"🌟 Nouveau VIP : {message.from_user.username or message.from_user.first_name}.")
        enregistrer_paiement_airtable(message.from_user.username or message.from_user.first_name, message.from_user.id, "VIP Access", "VIP Access")
        await bot.send_message(ADMIN_ID, "✅ VIP Access enregistré dans Airtable.")
        return

    await bot.send_message(message.chat.id, f"👋 Salut {message.from_user.first_name or 'toi'}, que veux-tu faire ?", reply_markup=keyboard)

# Gestion des boutons
@dp.message_handler(lambda message: message.text == "🔞Voir la vidéo du jour")
async def voir_video(message: types.Message):
    await bot.send_message(message.chat.id, "🎥 Voici ta vidéo du jour : https://buy.stripe.com/fZeg328Th4K67zW9AA")

@dp.message_handler(lambda message: message.text == "✨Discuter en tant que VIP")
async def discuter_vip(message: types.Message):
    await bot.send_message(message.chat.id, "🚀 Deviens VIP ici : https://buy.stripe.com/4gwg32fhF4K62fCdQR")

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

# Suppression des liens interdits
@dp.message_handler(lambda message: message.from_user.id != ADMIN_ID and ((message.text and "http" in message.text) or (message.caption and "http" in message.caption)), content_types=types.ContentType.ANY)
async def supprimer_liens_interdits(message: types.Message):
    text_to_check = message.text or message.caption or ""
    if lien_non_autorise(text_to_check):
        try:
            await bot.delete_message(chat_id=message.chat.id, message_id=message.message_id)
        except Exception as e:
            print(f"Erreur suppression lien externe : {e}")
        await bot.send_message(chat_id=message.chat.id, text="🚫 Les liens extérieurs sont interdits.")
        raise CancelHandler()

# --- Message relay (client -> admin & admin -> client) ---
pending_replies = {}

@dp.message_handler(lambda message: message.from_user.id != ADMIN_ID, content_types=types.ContentType.ANY)
async def relay_from_client(message: types.Message):
    try:
        sent_msg = None
        if message.text:
            sent_msg = await bot.forward_message(chat_id=ADMIN_ID, from_chat_id=message.chat.id, message_id=message.message_id)
        elif message.photo:
            sent_msg = await bot.send_photo(chat_id=ADMIN_ID, photo=message.photo[-1].file_id, caption=message.caption or "")
        elif message.video:
            sent_msg = await bot.send_video(chat_id=ADMIN_ID, video=message.video.file_id, caption=message.caption or "")
        elif message.document:
            sent_msg = await bot.send_document(chat_id=ADMIN_ID, document=message.document.file_id, caption=message.caption or "")
        elif message.voice:
            sent_msg = await bot.send_voice(chat_id=ADMIN_ID, voice=message.voice.file_id)
        elif message.audio:
            sent_msg = await bot.send_audio(chat_id=ADMIN_ID, audio=message.audio.file_id, caption=message.caption or "")
        else:
            await bot.send_message(chat_id=ADMIN_ID, text="📂 Un type de fichier non supporté a été reçu.")
            return

        if sent_msg:
            pending_replies[(sent_msg.chat.id, sent_msg.message_id)] = message.chat.id

    except Exception as e:
        await bot.send_message(chat_id=ADMIN_ID, text=f"❗Erreur lors du relais client -> admin.\n{e}")

@dp.message_handler(lambda message: message.from_user.id == ADMIN_ID, content_types=types.ContentType.ANY)
async def relay_from_admin(message: types.Message):
    if not message.reply_to_message:
        return

    user_id = None
    if message.reply_to_message.forward_from:
        user_id = message.reply_to_message.forward_from.id
    else:
        user_id = pending_replies.get((message.chat.id, message.reply_to_message.message_id))

    if not user_id:
        await bot.send_message(chat_id=ADMIN_ID, text="❗Impossible d'identifier le destinataire de la réponse.")
        return

    try:
        if message.text:
            await bot.send_message(chat_id=user_id, text=message.text)
        elif message.photo:
            await bot.send_photo(chat_id=user_id, photo=message.photo[-1].file_id, caption=message.caption or "")
        elif message.video:
            await bot.send_video(chat_id=user_id, video=message.video.file_id, caption=message.caption or "")
        elif message.document:
            await bot.send_document(chat_id=user_id, document=message.document.file_id, caption=message.caption or "")
        elif message.voice:
            await bot.send_voice(chat_id=user_id, voice=message.voice.file_id)
        elif message.audio:
            await bot.send_audio(chat_id=user_id, audio=message.audio.file_id, caption=message.caption or "")
        else:
            await bot.send_message(chat_id=ADMIN_ID, text="📂 Type de message non supporté pour le relais.")

    except Exception as e:
        await bot.send_message(chat_id=ADMIN_ID, text=f"❗Erreur lors du relais admin -> client.\n{e}")
