import email
from core import bot,dp
from aiogram import types
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from aiogram.dispatcher import Dispatcher
import requests
from datetime import datetime
from os import getenv
from detect_links_whitelist import detect_external_links

# --- CONFIGURATION AIRTABLE ---
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
        "Email": "vinteo.ac@gmail.com",
        "Date": datetime.now().isoformat()  # ✅ date ajoutée proprement
    }
}


    try:
        response = requests.post(url, json=data, headers=headers)
        print("Airtable response:", response.status_code, response.text)
        return response.status_code, response.text
    except Exception as e:
        print("Erreur lors de l’envoi à Airtable :", e)
        return None, str(e)


async def handle_start(message: types.Message):
    param = message.get_args()
    email = "vinteo@gmail.com"  # Exemple statique, à adapter avec une vraie saisie si souhaité


# Clavier avec emojis
keyboard = ReplyKeyboardMarkup(resize_keyboard=True)
keyboard.add(
    KeyboardButton("🔞Voir la vidéo du jour"),
    KeyboardButton("👀Je suis un voyeur"),
    KeyboardButton("✨Discuter en tant que VIP")
)

# ✅ AJOUT : initialisation du suivi des utilisateurs validés
utilisateurs_valides = set()


# Enregistrement des handlers avec bot explicite
def register_handlers(bot, dp: Dispatcher):
    from detect_links_whitelist import detect_external_links  # ✅ Ajout pour activer la détection des liens externes


@dp.message_handler(commands=['start'])
async def handle_start(message: types.Message):
    # ✅ Réinitialise si nécessaire
    if message.from_user.id in utilisateurs_valides:
        utilisateurs_valides.remove(message.from_user.id)

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
            utilisateurs_valides.add(message.from_user.id)  # ✅ Pour débloquer le chat
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
            "Tu fais maintenant partie de la communauté VIP ✨ ! Prépare-toi à recevoir du contenu privilégié."
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

    await bot.send_message(message.chat.id, "Chargement du menu...", reply_markup=types.ReplyKeyboardRemove())

    user_name = message.from_user.first_name or "toi"
    await bot.send_message(
        message.chat.id,
        f"Salut {user_name}, que veux-tu faire ?",
        reply_markup=keyboard
    )

        
        # Gestion des réponses aux boutons
    @dp.message_handler(lambda message: message.text == "🔞Voir la vidéo du jour")
    async def voir_video(message: types.Message):
        utilisateurs_valides.add(message.from_user.id)  # ✅ AJOUT : autorise cet utilisateur à écrire
        await bot.send_message(
            message.chat.id,
            "Voici le lien pour acheter la vidéo du jour en toute discrétion ! 💵 Une fois payé, tu recevras directement ta vidéo ici dans notre conversation 🤭 : https://buy.stripe.com/fZeg328Th4K67zW9AA"
        )

    @dp.message_handler(lambda message: message.text == "✨Discuter en tant que VIP")
    async def discuter_vip(message: types.Message):
        utilisateurs_valides.add(message.from_user.id)  # ✅ AJOUT : autorise cet utilisateur à écrire
        await bot.send_message(
            message.chat.id,
            "Je t'envoie ce lien pour confirmer ton adhésion à mon VIP ! Pas d'abonnement, juste un preuve de confiance d'un montant de (1 euro 🎁) pour enfin avoir des échanges privilégiés et plus intimes avec moi...🤭https://buy.stripe.com/4gwg32fhF4K62fCdQR"
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
        utilisateurs_valides.add(message.from_user.id)  # ✅ AJOUT : autorise cet utilisateur à écrire
        await bot.send_message(
            message.from_user.id,
            "Parfait. Voici le lien pour rejoindre le groupe VIP (1€) : https://buy.stripe.com/4gwg32fhF4K62fCdQR"
        )
        await bot.send_message(
        message.chat.id,
        "Voici à nouveau le menu principal. Que veux-tu faire ?",
        reply_markup=keyboard
    )
        # Detection des liens frauduleux

        @dp.message_handler(commands=["id"])
        async def send_admin_id(message: types.Message):
            admin_id = getenv("ADMIN_TELEGRAM_ID", "non défini")
        await message.answer(f"Ton ID Telegram est : {message.from_user.id}\nID enregistré dans le .env : {admin_id}")

        def register_handlers(bot, dp):
            from aiogram import types
            import detect_links_whitelist


        @dp.message_handler(commands=["id"])
        async def send_admin_id(message: types.Message):
            from os import getenv
        admin_id = getenv("ADMIN_TELEGRAM_ID", "non défini")
        await message.answer(f"Ton ID Telegram est : {message.from_user.id}\nID dans le .env : {admin_id}")

# ✅ AJOUT FINAL : blocage des messages libres tant que l'utilisateur n'a pas cliqué sur un bouton,
# sauf s'il s'agit d'un /start Stripe (comme /start paid39)
BOUTONS_AUTORISES = [
    "🔞Voir la vidéo du jour",
    "👀Je suis un voyeur",
    "✨Discuter en tant que VIP",
    "✅ Oui, je confirme (bannir)",
    "🚀 Non, je veux rejoindre le VIP"
]

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

        # ✅ Bloc chat libre :
@dp.message_handler(lambda message: message.from_user.id in utilisateurs_valides)
async def chat_libre(message: types.Message):
    await bot.send_message(
        chat_id=message.chat.id,
        text=f"✉️ {message.text}"
    )



