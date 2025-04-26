from core import bot, dp
from aiogram import types
import requests
import asyncio
from datetime import datetime

# === Config ===
ADMIN_ID = 7334072965  # ID Telegram de l'administrateur

# Clés API Airtable et paramètres (mettre vos propres valeurs si nécessaire)
AIRTABLE_API_KEY = "patAGB8w2HG44dvJy.8b57a2fe014dfcabc109214abf6c78aa2784b9701b6768ba40df7b32ab5df285"
BASE_ID = "appdA5tvdjXiktFzq"
TABLE_NAME = "Client Telegram"

# === Clavier principal (menu utilisateur) ===
keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
keyboard.add(
    types.KeyboardButton("🔞Voir la vidéo du jour"),
    types.KeyboardButton("👀Je suis un voyeur"),
    types.KeyboardButton("✨Discuter en tant que VIP")
)

# === Fonction de log Airtable ===
async def log_to_airtable(pseudo: str, user_id: int, type_acces: str, montant: float, contenu: str, email: str):
    """
    Enregistre une action (paiement, accès VIP, etc.) dans un tableau Airtable pour suivi.
    """
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
    # Envoi de la requête HTTP de manière asynchrone pour ne pas bloquer le bot
    try:
        await asyncio.to_thread(requests.post, url, json=data, headers=headers)
    except Exception as e:
        print(f"Erreur lors de l'envoi à Airtable : {e}")

# === Commande /start ===
@dp.message_handler(commands=['start'])
async def handle_start(message: types.Message):
    # Gère les différents paramètres de la commande /start (paiement ou accès VIP)
    param = message.get_args()
    prix_list = [9, 14, 19, 24, 29, 34, 39, 44, 49, 59, 69, 79, 89, 99]

    if param and param.startswith("paid") and param[4:].isdigit():
        # Paramètre indiquant un paiement (ex: "paid19")
        montant = int(param[4:])
        if montant in prix_list:
            await bot.send_message(
                message.chat.id,
                f"Merci pour ton paiement de {montant}€ 💖"
            )
            # Alerte administrateur pour le nouveau paiement
            await bot.send_message(
                ADMIN_ID,
                f"💰 Nouveau paiement de {montant}€ par {message.from_user.username or message.from_user.first_name}."
            )
            # Log du paiement dans Airtable
            await log_to_airtable(
                message.from_user.username or "",
                message.from_user.id,
                "Achat direct",
                float(montant),
                "Vidéo privée",
                "vinteo.ac@gmail.com"
            )
            return

    if param and (param == "vipaccess" or param == "vipaccess123"):
        # Paramètre indiquant un accès VIP validé
        await bot.send_message(message.chat.id, "Bienvenue dans le VIP ✨ !")
        # Notification à l'administrateur du nouvel accès VIP
        await bot.send_message(
            ADMIN_ID,
            f"🌟 Nouveau VIP : {message.from_user.username or message.from_user.first_name}."
        )
        # Log de l'accès VIP dans Airtable
        await log_to_airtable(
            message.from_user.username or "",
            message.from_user.id,
            "VIP",
            1.00,
            "Accès VIP",
            "vinteo.ac@gmail.com"
        )
        return

    # Réponse par défaut pour /start sans paramètre particulier
    await bot.send_message(
        message.chat.id,
        f"Salut {message.from_user.first_name or 'toi'}, que veux-tu faire ?",
        reply_markup=keyboard
    )

# === Gestion des boutons du menu principal ===
@dp.message_handler(lambda message: message.text == "🔞Voir la vidéo du jour")
async def voir_video(message: types.Message):
    # Envoie le lien de la vidéo du jour
    await bot.send_message(
        message.chat.id,
        "Voici la vidéo du jour 🔥 : https://buy.stripe.com/fZeg328Th4K67zW9AA"
    )

@dp.message_handler(lambda message: message.text == "✨Discuter en tant que VIP")
async def discuter_vip(message: types.Message):
    # Fournit le lien d'achat pour accéder au chat VIP
    await bot.send_message(
        message.chat.id,
        "Pour discuter en VIP, confirme ton accès ici : https://buy.stripe.com/4gwg32fhF4K62fCdQR"
    )

@dp.message_handler(lambda message: message.text == "👀Je suis un voyeur")
async def choix_voyeur(message: types.Message):
    # Demande à l'utilisateur de confirmer s'il veut rester simple spectateur (voyeur)
    clavier_confirmation = types.ReplyKeyboardMarkup(resize_keyboard=True)
    clavier_confirmation.add(
        types.KeyboardButton("✅ Oui je confirme (bannir)"),
        types.KeyboardButton("🚀 Non, je veux rejoindre le VIP")
    )
    await bot.send_message(
        message.chat.id,
        "Confirme si tu veux vraiment rester simple spectateur :",
        reply_markup=clavier_confirmation
    )

@dp.message_handler(lambda message: message.text == "✅ Oui je confirme (bannir)")
async def confirmer_voyeur(message: types.Message):
    # Gère la confirmation du statut de voyeur (non VIP)
    await bot.send_message(
        message.chat.id,
        "Ok, tu seras retiré du VIP."
    )
    # Note: On pourrait ajouter ici une action pour bannir ou marquer l'utilisateur comme non VIP définitivement.

@dp.message_handler(lambda message: message.text == "🚀 Non, je veux rejoindre le VIP")
async def rejoindre_vip(message: types.Message):
    # Fournit le lien pour rejoindre le VIP à l'utilisateur qui change d'avis
    await bot.send_message(
        message.chat.id,
        "Rejoins le VIP ici : https://buy.stripe.com/4gwg32fhF4K62fCdQR",
        reply_markup=keyboard
    )

# === Détection et suppression des liens non whitelistés ===
@dp.message_handler(lambda message: message.from_user.id != ADMIN_ID and ((message.text and "http" in message.text) or (message.caption and "http" in message.caption)))
async def detect_external_links(message: types.Message):
    # Supprime tout message contenant un lien non autorisé par la whitelist
    WHITELIST_LINKS = [
        "https://novapulseonline.wixsite.com/",
        "https://buy.stripe.com/"
    ]
    # Récupère le contenu textuel du message (texte ou légende)
    content = message.text if message.text else (message.caption or "")
    # Vérifie si le contenu contient un lien non autorisé
    for part in content.split():
        if part.startswith("http://") or part.startswith("https://"):
            lien = part
            # Si aucun domaine autorisé n'est présent dans ce lien, on le considère comme externe interdit
            if not any(allowed in lien for allowed in WHITELIST_LINKS):
                try:
                    await bot.delete_message(chat_id=message.chat.id, message_id=message.message_id)
                    await bot.send_message(chat_id=message.chat.id, text="⚠️ Les liens extérieurs ne sont pas autorisés ici.")
                    print(f"❌ Lien bloqué et message supprimé : {lien}")
                except Exception as e:
                    print(f"Erreur suppression lien : {e}")
                return  # Sort dès qu'un lien interdit a été supprimé

# === Relais des messages client -> admin (texte, photo, vidéo, document, etc.) ===
@dp.message_handler(lambda message: message.from_user.id != ADMIN_ID)
async def relay_all_from_client(message: types.Message):
    # Transfère tous les messages des utilisateurs (non-admin) vers l'administrateur
    try:
        await bot.forward_message(chat_id=ADMIN_ID, from_chat_id=message.chat.id, message_id=message.message_id)
    except Exception as e:
        print(f"Erreur lors du forward client ➔ admin : {e}")

# === Relais des messages admin -> client (texte, photo, vidéo, document, etc.) ===
@dp.message_handler(lambda message: message.from_user.id == ADMIN_ID)
async def relay_all_from_admin(message: types.Message):
    # Permet à l'admin de répondre à un utilisateur en répondant au message transféré du bot
    if message.reply_to_message and message.reply_to_message.forward_from:
        target_client_id = message.reply_to_message.forward_from.id
        try:
            await bot.copy_message(chat_id=target_client_id, from_chat_id=message.chat.id, message_id=message.message_id)
        except Exception as e:
            await bot.send_message(chat_id=ADMIN_ID, text="❗Erreur : impossible d'envoyer le média.")
    else:
        # Si l'admin écrit sans répondre à un message transféré, on lui rappelle comment répondre
        await bot.send_message(chat_id=ADMIN_ID, text="❗Merci de répondre en cliquant sur un message transféré.")
