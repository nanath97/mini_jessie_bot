from core import bot, dp
from aiogram import types
import os
from datetime import datetime
from aiogram.dispatcher.handler import CancelHandler

# === CONFIGURATION ===
AIRTABLE_API_KEY = "patAGB8w2HG44dvJy.8b57a2fe014dfcabc109214ab5f6c78aa2784b9701b6768ba40df7b32ab5df285"
BASE_ID = "appdA5tvdjXiktFzq"
TABLE_NAME = "Client Telegram"
ADMIN_ID = 7334072965

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


# Liste des prix autorisés
prix_list = [9, 14, 19, 24, 29, 34, 39, 44, 49, 59, 69, 79, 89, 99]

# Liste blanche des liens autorisés
WHITELIST_LINKS = [
    "https://novapulseonline.wixsite.com/",
    "https://buy.stripe.com/",
    "https://t.me/mini_jessie_bot?startpaid"
]

# Fonction de détection de lien non autorisé
def lien_non_autorise(text):
    return any(part.startswith("http") and not any(allowed in part for allowed in WHITELIST_LINKS) for part in text.split())

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
            return

    if param in ["vipaccess", "vipaccess123"]:
        await bot.send_message(message.chat.id, "✨ Bienvenue dans le VIP !")
        await bot.send_message(ADMIN_ID, f"🌟 Nouveau VIP : {message.from_user.username or message.from_user.first_name}.")
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

# Suppression des liens interdits dans les messages des utilisateurs (texte ou légende)
@dp.message_handler(lambda message: message.from_user.id != ADMIN_ID and (
                                   (message.text and "http" in message.text) or 
                                   (message.caption and "http" in message.caption)),
                    content_types=types.ContentType.ANY)
async def supprimer_liens_interdits(message: types.Message):
    text_to_check = message.text or message.caption or ""
    if lien_non_autorise(text_to_check):
        try:
            await bot.delete_message(chat_id=message.chat.id, message_id=message.message_id)
        except Exception as e:
            print(f"Erreur suppression lien externe : {e}")
        # Avertir l'utilisateur
        await bot.send_message(chat_id=message.chat.id, text="🚫 Les liens extérieurs sont interdits.")
        # Stoppe la propagation de cet événement à d'autres handlers
        raise CancelHandler()

# Dictionnaire pour faire correspondre les messages envoyés à l'admin avec l'utilisateur d'origine
pending_replies = {}

# Relais Client -> Admin
@dp.message_handler(lambda message: message.from_user.id != ADMIN_ID, content_types=types.ContentType.ANY)
async def relay_from_client(message: types.Message):
    """
    Relais des messages du client vers l'administrateur.
    Gère texte, photo, vidéo, document, audio et voice en utilisant les file_id Telegram pour éviter le stockage local.
    """
    try:
        sent_msg = None
        if message.text:
            # Transférer le message texte tel quel (conserve la référence de l'utilisateur)
            sent_msg = await bot.forward_message(chat_id=ADMIN_ID, from_chat_id=message.chat.id, message_id=message.message_id)
        elif message.photo:
            # Envoyer la photo et sa légende à l'admin
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
            # Type non supporté (ex. sticker, contact)
            await bot.send_message(chat_id=ADMIN_ID, text="📂 Un type de fichier non supporté a été reçu.")
            return  # Sortie anticipée sans erreur

        # Si un message a bien été envoyé à l'admin, lier son ID au chat utilisateur d'origine
        if sent_msg:
            pending_replies[(sent_msg.chat.id, sent_msg.message_id)] = message.chat.id

    except Exception as e:
        # Informer l'admin de l'échec du transfert
        await bot.send_message(chat_id=ADMIN_ID, text=f"❗Erreur lors du relais client -> admin.\n{e}")
        print(f"Erreur relay client -> admin : {e}")

# Relais Admin -> Client
@dp.message_handler(lambda message: message.from_user.id == ADMIN_ID, content_types=types.ContentType.ANY)
async def relay_from_admin(message: types.Message):
    """
    Relais des réponses de l'administrateur vers le client d'origine.
    L'administrateur doit répondre (reply) à un message du bot pour que sa réponse soit relayée.
    """
    if not message.reply_to_message:
        return  # Ignorer si le message de l'admin n'est pas une réponse à un message existant

    # Obtenir l'ID de l'utilisateur cible soit via la référence du message forwardé, soit via le dictionnaire
    user_id = None
    if message.reply_to_message.forward_from:
        user_id = message.reply_to_message.forward_from.id
    else:
        user_id = pending_replies.get((message.chat.id, message.reply_to_message.message_id))

    if not user_id:
        await bot.send_message(chat_id=ADMIN_ID, text="❗Impossible d'identifier le destinataire de la réponse.")
        return

    try:
        # Relayer en fonction du type de contenu du message de l'admin
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
            await bot.send_message(chat_id=ADMIN_ID, text="📂 Le type de message de l'admin n'est pas supporté pour le relais.")
            return

    except Exception as e:
        # Alerter l'admin en cas d'erreur d'envoi
        await bot.send_message(chat_id=ADMIN_ID, text=f"❗Erreur lors du relais admin -> client.\n{e}")
        print(f"Erreur relay admin -> client : {e}")