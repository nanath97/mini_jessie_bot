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

# Lien pour rejoindre le VIP
VIP_JOIN_LINK = "https://buy.stripe.com/4gwg32fhF4K62fCdQR"

# Création du clavier principal
keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
keyboard.add(
    types.KeyboardButton("🔞Voir la vidéo du jour"),
    types.KeyboardButton("👀Je suis un voyeur"),
    types.KeyboardButton("✨Discuter en tant que VIP")
)

# Utilisateurs validés (ayant accès au chat libre)
declaring_utilisateurs_valides = set()

# Liste des textes de boutons autorisés (pour ne pas être bloqués)
ALLOWED_TEXTS = [
    "🔞Voir la vidéo du jour",
    "👀Je suis un voyeur",
    "✨Discuter en tant que VIP",
    "✅ Oui je confirme",
    "🚀 Non je veux rejoindre le VIP"
]

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
        part.startswith("http") 
        and not any(allowed in part for allowed in WHITELIST_LINKS) 
        for part in text.split()
    )

# Commande /start
async def handle_start(message: types.Message):
    param = message.get_args()

    if param:
        if param.startswith("paid") and param[4:].isdigit():
            montant = int(param[4:])
            if montant in prix_list:
                await bot.send_message(
                    message.chat.id,
                    f"Merci pour ton paiement de {montant}€ 💖"
                )
                declaring_utilisateurs_valides.add(message.from_user.id)
                log_to_airtable(
                    message.from_user.username, message.from_user.id,
                    "Achat direct", montant, "Vidéo privée", "email@exemple.com"
                )
                return
        elif param == "vipaccess":
            # Accès VIP direct
            declaring_utilisateurs_valides.add(message.from_user.id)
            log_to_airtable(
                message.from_user.username, message.from_user.id,
                "Accès VIP", 0, "Accès VIP", "email@exemple.com"
            )
            await bot.send_message(
                message.chat.id,
                f"Bienvenue {message.from_user.first_name or 'à toi'}, tu as désormais un accès VIP !",
                reply_markup=keyboard
            )
            return

    # Message de bienvenue par défaut si aucun paramètre spécial
    await bot.send_message(
        message.chat.id,
        f"Salut {message.from_user.first_name or 'toi'}, que veux-tu faire ?",
        reply_markup=keyboard
    )

# Gestion des boutons
async def voir_video(message: types.Message):
    # Envoi de la vidéo du jour (accès libre)
    await bot.send_message(
        message.chat.id,
        "Voici la vidéo du jour 🔥!"
    )

async def discuter_vip(message: types.Message):
    if message.from_user.id not in declaring_utilisateurs_valides:
        # Si l'utilisateur n'est pas VIP, on l’invite à le devenir
        await bot.send_message(
            message.chat.id,
            f"✨ Cette section est réservée aux membres VIP. Pour nous rejoindre, utilise ce lien : {VIP_JOIN_LINK}",
            reply_markup=keyboard
        )
    else:
        # Si déjà VIP
        await bot.send_message(
            message.chat.id,
            "✨ Tu as déjà accès à l'espace VIP, tu peux discuter librement."
        )

async def voyeur(message: types.Message):
    # Demande de confirmation pour rester spectateur ou devenir VIP
    keyboard_confirmation = types.ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard_confirmation.add(
        types.KeyboardButton("✅ Oui je confirme"),
        types.KeyboardButton("🚀 Non je veux rejoindre le VIP")
    )
    await bot.send_message(
        message.chat.id,
        "Confirme si tu veux rester un simple spectateur ou rejoindre le VIP.",
        reply_markup=keyboard_confirmation
    )

async def confirmer_voyeur(message: types.Message):
    # L'utilisateur choisit de rester spectateur (accès limité)
    await bot.send_message(
        message.chat.id,
        "Tu as choisi de rester un simple spectateur. Accès limité.",
        reply_markup=keyboard
    )

async def rejoindre_vip(message: types.Message):
    # Fournir le lien d’adhésion VIP
    await bot.send_message(
        message.chat.id,
        f"Parfait ! Voici le lien pour rejoindre le VIP : {VIP_JOIN_LINK}",
        reply_markup=keyboard
    )

async def detecter_lien_externe(message: types.Message):
    # Supprime les liens extérieurs non autorisés et avertit l'utilisateur
    if lien_non_autorise(message.text):
        try:
            await bot.delete_message(chat_id=message.chat.id, message_id=message.message_id)
        except Exception as e:
            print("Erreur suppression lien externe :", e)
        await bot.send_message(
            chat_id=message.chat.id,
            text="🛘 Les liens extérieurs ne sont pas autorisés."
        )

async def chat_libre(message: types.Message):
    # Gère le chat libre avec l'utilisateur VIP validé (à implémenter)
    pass

# Enregistrement des handlers pour FastAPI/Render
_handlers_registered = False
def register_handlers(bot_instance=None, dp_instance=None):
    global _handlers_registered
    if _handlers_registered:
        return
    dp_obj = dp_instance or dp
    # Commande /start
    dp_obj.register_message_handler(handle_start, commands=['start'])
    # Boutons du menu principal
    dp_obj.register_message_handler(voir_video, lambda message: message.text == "🔞Voir la vidéo du jour")
    dp_obj.register_message_handler(voyeur, lambda message: message.text == "👀Je suis un voyeur")
    dp_obj.register_message_handler(discuter_vip, lambda message: message.text == "✨Discuter en tant que VIP")
    # Boutons de confirmation VIP
    dp_obj.register_message_handler(confirmer_voyeur, lambda message: message.text == "✅ Oui je confirme")
    dp_obj.register_message_handler(rejoindre_vip, lambda message: message.text == "🚀 Non je veux rejoindre le VIP")
    

    # Suppression des liens non whitelistés (pour utilisateurs validés)
    dp_obj.register_message_handler(
        detecter_lien_externe,
        lambda message: "http" in message.text and message.from_user.id in declaring_utilisateurs_valides
    )
    # Chat libre pour utilisateurs validés (VIP)
    dp_obj.register_message_handler(
        chat_libre,
        lambda message: message.from_user.id in declaring_utilisateurs_valides
    )
    _handlers_registered = True
