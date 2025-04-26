from core import bot, dp
from aiogram import types
import requests
from datetime import datetime

# === Config ===
ADMIN_ID = 7334072965  # Remplace 123456789 par ton vrai ID Telegram admin

AIRTABLE_API_KEY = "patAGB8w2HG44dvJy.8b57a2fe014dfcabc109214abf6c78aa2784b9701b6768ba40df7b32ab5df285"
BASE_ID = "appdA5tvdjXiktFzq"
TABLE_NAME = "Client Telegram"

# === Clavier principal ===
keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
keyboard.add(
    types.KeyboardButton("🔞Voir la vidéo du jour"),
    types.KeyboardButton("👀Je suis un voyeur"),
    types.KeyboardButton("✨Discuter en tant que VIP")
)

# === Log Airtable ===
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
    requests.post(url, json=data, headers=headers)

# === /start Handler ===
@dp.message_handler(commands=["start"])
async def handle_start(message: types.Message):
    param = message.get_args()
    prix_list = [9, 14, 19, 24, 29, 34, 39, 44, 49, 59, 69, 79, 89, 99]

    if param.startswith("paid") and param[4:].isdigit():
        montant = int(param[4:])
        if montant in prix_list:
            await bot.send_message(message.chat.id, f"Merci pour ton paiement de {montant}€ 💖")
            await bot.send_message(ADMIN_ID, f"💰 Nouveau paiement de {montant}€ par {message.from_user.username or message.from_user.first_name}.")
            log_to_airtable(message.from_user.username, message.from_user.id, "Achat direct", montant, "Vidéo privée", "vinteo.ac@gmail.com")
            return

    if param == "vipaccess" or param == "vipaccess123":
        await bot.send_message(message.chat.id, "Bienvenue dans le VIP ✨ !")
        await bot.send_message(ADMIN_ID, f"🌟 Nouveau VIP : {message.from_user.username or message.from_user.first_name}.")
        log_to_airtable(message.from_user.username, message.from_user.id, "VIP", 1.00, "Accès VIP", "vinteo.ac@gmail.com")
        return

    await bot.send_message(message.chat.id, f"Salut {message.from_user.first_name or 'toi'}, que veux-tu faire ?", reply_markup=keyboard)

# === Gestion des boutons ===
@dp.message_handler(lambda message: message.text == "🔞Voir la vidéo du jour")
async def voir_video(message: types.Message):
    await bot.send_message(message.chat.id, "Voici la vidéo du jour 🔥 : https://buy.stripe.com/fZeg328Th4K67zW9AA")

@dp.message_handler(lambda message: message.text == "✨Discuter en tant que VIP")
async def discuter_vip(message: types.Message):
    await bot.send_message(message.chat.id, "Pour discuter en VIP, confirme ton accès ici : https://buy.stripe.com/4gwg32fhF4K62fCdQR")

@dp.message_handler(lambda message: message.text == "👀Je suis un voyeur")
async def confirmer_voyeur(message: types.Message):
    clavier_confirmation = types.ReplyKeyboardMarkup(resize_keyboard=True)
    clavier_confirmation.add(
        types.KeyboardButton("✅ Oui je confirme (bannir)"),
        types.KeyboardButton("🚀 Non, je veux rejoindre le VIP")
    )
    await bot.send_message(message.chat.id, "Confirme si tu veux vraiment rester simple spectateur :", reply_markup=clavier_confirmation)

@dp.message_handler(lambda message: message.text == "✅ Oui je confirme (bannir)")
async def bannir_utilisateur(message: types.Message):
    await bot.send_message(message.chat.id, "Ok, tu seras retiré du VIP.")

@dp.message_handler(lambda message: message.text == "🚀 Non, je veux rejoindre le VIP")
async def rejoindre_vip(message: types.Message):
    await bot.send_message(message.chat.id, "Rejoins le VIP ici : https://buy.stripe.com/4gwg32fhF4K62fCdQR", reply_markup=keyboard)

# === BLOQUER LES LIENS NON AUTORISÉS
@dp.message_handler(lambda message: message.text and "http" in message.text and message.from_user.id != ADMIN_ID)
async def detect_external_links(message: types.Message):
    WHITELIST_LINKS = [
        "https://novapulseonline.wixsite.com/",
        "https://buy.stripe.com/"
    ]

    # Si aucun lien autorisé trouvé dans le message ➔ on supprime
    if not any(allowed in message.text for allowed in WHITELIST_LINKS):
        try:
            await bot.delete_message(chat_id=message.chat.id, message_id=message.message_id)
            await bot.send_message(chat_id=message.chat.id, text="⚠️ Les liens extérieurs ne sont pas autorisés ici.")
            print(f"❌ Lien bloqué : {message.text}")
        except Exception as e:
            print(f"Erreur suppression lien : {e}")





# === RELAY CLIENT → ADMIN (TOUT TYPE DE MESSAGE)
@dp.message_handler(lambda message: message.from_user.id != ADMIN_ID)
async def relay_all_from_client(message: types.Message):
    try:
        await bot.forward_message(chat_id=ADMIN_ID, from_chat_id=message.chat.id, message_id=message.message_id)
    except Exception as e:
        print(f"Erreur lors du forward client ➔ admin : {e}")

# === RELAY ADMIN → CLIENT (TOUT TYPE DE MESSAGE)
@dp.message_handler(lambda message: message.from_user.id == ADMIN_ID)
async def relay_all_from_admin(message: types.Message):
    if message.reply_to_message and message.reply_to_message.forward_from:
        target_client_id = message.reply_to_message.forward_from.id
        try:
            await bot.copy_message(chat_id=target_client_id, from_chat_id=message.chat.id, message_id=message.message_id)
        except Exception as e:
            await bot.send_message(chat_id=ADMIN_ID, text="❗Erreur : impossible d’envoyer le média.")
    else:
        await bot.send_message(chat_id=ADMIN_ID, text="❗Merci de répondre en cliquant sur un message transféré.")
