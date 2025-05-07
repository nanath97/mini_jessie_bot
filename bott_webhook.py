from core import bot, dp
from aiogram import types
import os
from datetime import datetime
from aiogram.dispatcher.handler import CancelHandler
import requests
from core import authorized_users
from detect_links_whitelist import lien_non_autorise


# 1.=== Variables globales ===
DEFAULT_FLOU_IMAGE_FILE_ID = "AgACAgEAAxkBAAIOgWgSLV1I3pOt7vxnpci_ba-hb9UXAAK6rjEbM2KQRDdrQA-mqmNwAQADAgADeAADNgQ" # Remplace par le vrai file_id Telegram


# Fonction de détection de lien non autorisé
ALLOWED_DOMAINS = os.getenv("ALLOWED_DOMAINS", "").split(",")

# --- CONFIGURATION AIRTABLE TEST ---
AIRTABLE_API_KEY = os.getenv("AIRTABLE_API_KEY")
BASE_ID = os.getenv("BASE_ID")
TABLE_NAME = os.getenv("TABLE_NAME")
SELLER_EMAIL = os.getenv("SELLER_EMAIL")  # ✅ ici



# ADMIN ID
ADMIN_ID = 7334072965 # 22
DIRECTEUR_ID = 7334072965  # ID personnel au ceo pour avertir des fraudeurs

# === MEDIA EN ATTENTE ===
contenus_en_attente = {}  # { user_id: {"file_id": ..., "type": ..., "caption": ...} }
paiements_en_attente_par_user = set()  # Set de user_id qui ont payé
# === FIN MEDIA EN ATTENTE ===


# === Statistiques ===

@dp.message_handler(commands=["stat"])
async def handle_stat(message: types.Message):
    if not SELLER_EMAIL:
        await bot.send_message(message.chat.id, "❌ Erreur : adresse email non configurée.")
        return

    await bot.send_message(message.chat.id, "📥 Traitement de tes statistiques de vente en cours...")

    try:
        url = f"https://api.airtable.com/v0/{BASE_ID}/{TABLE_NAME.replace(' ', '%20')}"
        headers = {
            "Authorization": f"Bearer {AIRTABLE_API_KEY}"
        }

        response = requests.get(url, headers=headers)
        data = response.json()

        ventes_totales = 0
        ventes_jour = 0
        contenus_vendus = 0
        emails_vip = set()

        today = datetime.now().date().isoformat()

        for record in data.get("records", []):
            fields = record.get("fields", {})
            email = fields.get("Email", "")
            date_str = fields.get("Date", "")
            montant = float(fields.get("Montant", 0))
            type_acces = fields.get("Type acces", "")

            if email == SELLER_EMAIL:
                ventes_totales += montant

                if type_acces.lower() != "vip":
                    contenus_vendus += 1

                if date_str.startswith(today):
                    ventes_jour += montant

                if type_acces.lower() == "vip":
                    emails_vip.add(email)

        clients_vip = len(emails_vip)
        benefice_net = round(ventes_totales * 0.94, 2)

        message_final = (
            f"📊 Tes statistiques de vente :\n\n"
            f"💰 Ventes du jour : {ventes_jour}€\n"
            f"💶 Ventes totales : {ventes_totales}€\n"
            f"📦 Contenus vendus total : {contenus_vendus}\n"
            f"🌟 Clients VIP : {clients_vip}\n"
            f"📈 Bénéfice estimé net : {benefice_net}€\n\n"
            f"_Le bénéfice tient compte d’une commission de 6 %._"
        )

        await bot.send_message(message.chat.id, message_final, parse_mode="Markdown")

    except Exception as e:
        print(f"Erreur dans /stat : {e}")
        await bot.send_message(message.chat.id, "❌ Une erreur est survenue lors de la récupération des statistiques.")

# Fin de la fonction des stats

# DEBUT de la fonction du proprietaire ! Ne pas toucher

@dp.message_handler(commands=["nath"])
async def handle_nath_global_stats(message: types.Message):
    if message.from_user.id != int(ADMIN_ID):
        await bot.send_message(message.chat.id, "❌ Tu n'as pas l'autorisation d'utiliser cette commande.")
        return

    await bot.send_message(message.chat.id, "🕓 Récupération des statistiques globales en cours...")

    try:
        url = f"https://api.airtable.com/v0/{BASE_ID}/{TABLE_NAME.replace(' ', '%20')}"
        headers = {
            "Authorization": f"Bearer {AIRTABLE_API_KEY}"
        }

        response = requests.get(url, headers=headers)
        data = response.json()

        ventes_par_email = {}

        for record in data.get("records", []):
            fields = record.get("fields", {})
            email = fields.get("Email", "")
            montant = float(fields.get("Montant", 0))

            if not email:
                continue

            if email not in ventes_par_email:
                ventes_par_email[email] = 0
            ventes_par_email[email] += montant

        if not ventes_par_email:
            await bot.send_message(message.chat.id, "Aucune donnée trouvée dans Airtable.")
            return

        lignes = [f"📊 Récapitulatif global :\n"]

        for email, total in ventes_par_email.items():
            benefice = round(total * 0.94, 2)
            lignes.append(f"• {email} → {total:.2f} € (bénéfice : {benefice:.2f} €)")

        lignes.append("\n_Le bénéfice net tient compte d’une commission de 6 %._")

        await bot.send_message(message.chat.id, "\n".join(lignes), parse_mode="Markdown")

    except Exception as e:
        print(f"Erreur dans /nath : {e}")
        await bot.send_message(message.chat.id, "❌ Une erreur est survenue lors du traitement des statistiques.")

# FIN de la fonction du propriétaire 

# Liste des clients bannis par admin
ban_list = {}
@dp.message_handler(commands=['supp'])
async def bannir_client(message: types.Message):
    if not message.reply_to_message:
        await message.reply("❌ Utilisez cette commande en réponse au message du client à retirer.")
        return

    user_id = None
    if message.reply_to_message.forward_from:
        user_id = message.reply_to_message.forward_from.id
    else:
        user_id = pending_replies.get((message.chat.id, message.reply_to_message.message_id))

    if not user_id:
        await message.reply("❌ Impossible d’identifier le client. Réponds bien à un message transféré par le bot.")
        return

    admin_id = message.from_user.id

    if admin_id not in ban_list:
        ban_list[admin_id] = []

    if user_id not in ban_list[admin_id]:
        ban_list[admin_id].append(user_id)

        await message.reply("✅ Le client a été retiré avec succès.")
        try:
            await bot.send_message(user_id, "❌ Désolée mais vous avez été retiré du groupe VIP.")
        except Exception as e:
            print(f"Erreur lors de l'envoi du message au client banni : {e}")
            await message.reply("ℹ️ Le client est bien banni, mais je n’ai pas pu lui envoyer le message (permissions Telegram).")
    else:
        await message.reply("ℹ️ Ce client est déjà retiré.")


@dp.message_handler(commands=['unsupp'])
async def reintegrer_client(message: types.Message):
    if not message.reply_to_message:
        await message.reply("❌ Utilisez cette commande en réponse au message du client à réintégrer.")
        return

    user_id = None
    if message.reply_to_message.forward_from:
        user_id = message.reply_to_message.forward_from.id
    else:
        user_id = pending_replies.get((message.chat.id, message.reply_to_message.message_id))

    if not user_id:
        await message.reply("❌ Impossible d’identifier le client. Réponds bien à un message transféré par le bot.")
        return

    admin_id = message.from_user.id

    if admin_id in ban_list and user_id in ban_list[admin_id]:
        ban_list[admin_id].remove(user_id)

        await message.reply("✅ Le client a été réintégré avec succès.")
        try:
            await bot.send_message(user_id, "✅ Vous avez été réintégré au sein du groupe VIP !")
        except Exception as e:
            print(f"Erreur lors de l'envoi du message au client réintégré : {e}")
            await message.reply("ℹ️ Réintégré, mais le message n’a pas pu être envoyé (permissions Telegram).")

    else:
        await message.reply("ℹ️ Ce client n’était pas retiré.")

# Mise sous forme de boutons : bannissement

@dp.message_handler(lambda message: message.text == "❌ Bannir le client" and message.reply_to_message and message.from_user.id == ADMIN_ID)
async def bouton_bannir(message: types.Message):
    forwarded = message.reply_to_message.forward_from
    if not forwarded:
        await message.reply("❌ Tu dois répondre à un message transféré du client.")
        return

    user_id = forwarded.id
    ban_list.setdefault(message.from_user.id, set()).add(user_id)
    await message.reply(f"🚫 Le client a été banni avec succès.")
    try:
        await bot.send_message(user_id, "❌ Tu as été retiré. Tu ne peux plus me recontacter.")
    except Exception as e:
        print(f"Erreur d'envoi au client banni : {e}")
        await message.reply("ℹ️ Le client est banni, mais je n’ai pas pu lui envoyer le message.")


@dp.message_handler(lambda message: message.text == "✅ Réintégrer le client" and message.reply_to_message and message.from_user.id == ADMIN_ID)
async def bouton_reintegrer(message: types.Message):
    forwarded = message.reply_to_message.forward_from
    if not forwarded:
        await message.reply("❌ Tu dois répondre à un message transféré du client.")
        return

    user_id = forwarded.id
    if user_id in ban_list.get(message.from_user.id, set()):
        ban_list[message.from_user.id].remove(user_id)
        await message.reply(f"✅ Le client a été réintégré.")
        try:
            await bot.send_message(user_id, "✅ Tu as été réintégré, tu peux me recontacter.")
        except Exception as e:
            print(f"Erreur d'envoi au client réintégré : {e}")
            await message.reply("ℹ️ Réintégré, mais je n’ai pas pu lui envoyer le message.")
    else:
        await message.reply("ℹ️ Ce client n’était pas retiré.")

# Liste des prix autorisés
prix_list = [9, 14, 19, 24, 29, 34, 39, 44, 49, 59, 69, 79, 89, 99]

# Liste blanche des liens autorisés
WHITELIST_LINKS = [
    "https://novapulseonline.wixsite.com/",
    "https://buy.stripe.com/",
    "https://t.me/mini_jessie_bot?start=cdan" # 22 Rajouter à la ligne en bas le lien propre de l'admin
]

def lien_non_autorise(text):
    words = text.split()
    for word in words:
        if word.startswith("http://") or word.startswith("https://"):
            if not any(domain.strip() in word for domain in ALLOWED_DOMAINS):
                return True
    return False

@dp.message_handler(lambda message: (message.text and ("http://" in message.text or "https://" in message.text)) or (message.caption and ("http://" in message.caption or "https://" in message.caption)), content_types=types.ContentType.ANY)
async def verifier_les_liens_uniquement(message: types.Message):
    text_to_check = message.text or message.caption or ""
    if lien_non_autorise(text_to_check):
        try:
            await bot.delete_message(chat_id=message.chat.id, message_id=message.message_id)
            await bot.send_message(chat_id=message.chat.id, text="🚫 Les liens extérieurs sont interdits.")
            
            # Message perso au CEO pour avertir des fraudeurs
            await bot.send_message(DIRECTEUR_ID,
                                   f"🚨 Tentative de lien interdit détectée !\n\n"
            f"👤 User: {message.from_user.username or message.from_user.first_name}\n"
            f"🆔 ID: {message.from_user.id}\n"
            f"🔗 Lien envoyé : {text_to_check}")

            print(f"🔴 Lien interdit supprimé : {text_to_check}")
        except Exception as e:
            print(f"Erreur lors de la suppression du lien interdit : {e}")
        raise CancelHandler()

# Fonction pour ajouter un paiement à Airtable 22 Changer l'adresse mail par celui de l'admin
def log_to_airtable(pseudo, user_id, type_acces, montant, contenu="Paiement Telegram", email="vinteo.ac@gmail.com"): 
    if not type_acces:
        type_acces = "Paiement"
    url = f"https://api.airtable.com/v0/{BASE_ID}/{TABLE_NAME.replace(' ', '%20')}"
    headers = {
        "Authorization": f"Bearer {AIRTABLE_API_KEY}",
        "Content-Type": "application/json"
    }

    now = datetime.now()

    data = {
        "fields": {
            "Pseudo Telegram": pseudo or "-",
            "ID Telegram": str(user_id),
            "Type acces": str(type_acces),
            "Montant": float(montant),
            "Contenu": contenu,
            "Email": email,
            "Date": now.isoformat(),
            "Mois": now.strftime("%Y-%m")  # ← C’est ça qui te permet de filtrer le mois
        }
    }

    print(data)  # Debug temporaire pour vérifier ce qu'on envoie
    response = requests.post(url, json=data, headers=headers)
    if response.status_code != 200:
        print(f"Erreur Airtable : {response.text}")
    else:
        print("✅ Paiement ajouté dans Airtable avec succès !")

# Création du clavier

keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
keyboard.add(
    types.KeyboardButton("👀Je suis un voyeur"),
    types.KeyboardButton("✨Discuter en tant que VIP")
)
keyboard_admin = types.ReplyKeyboardMarkup(resize_keyboard=True)
keyboard_admin.add(
    types.KeyboardButton("📖 Commandes"),
    types.KeyboardButton("📊 Statistiques")
)
keyboard_admin.add(# TEST bouton admin
    types.KeyboardButton("❌ Bannir le client"),
    types.KeyboardButton("✅ Réintégrer le client")
)

# Détecter le paiement /start=cdan... et envoyer si contenu déjà prêt ===
@dp.message_handler(commands=["start"])
async def handle_start(message: types.Message):
    param = message.get_args()

    if param.startswith("cdan") and param[4:].isdigit():
        montant = int(param[4:])
        if montant in prix_list:

            authorized_users.add(message.from_user.id)

            # --- Envoi du média si déjà prêt ---
            user_id = message.from_user.id
            if user_id in contenus_en_attente:
                contenu = contenus_en_attente[user_id]
                if contenu["type"] == types.ContentType.PHOTO:
                    await bot.send_photo(chat_id=user_id, photo=contenu["file_id"], caption=contenu["caption"])
                elif contenu["type"] == types.ContentType.VIDEO:
                    await bot.send_video(chat_id=user_id, video=contenu["file_id"], caption=contenu["caption"])
                elif contenu["type"] == types.ContentType.DOCUMENT:
                    await bot.send_document(chat_id=user_id, document=contenu["file_id"], caption=contenu["caption"])
                del contenus_en_attente[user_id]
            else:
                paiements_en_attente_par_user.add(user_id)

            # --- Message automatique habituel ---
            await bot.send_message(message.chat.id, f"✅ Merci pour ton paiement de {montant}€ 💖 ! Ton contenu arrive dans quelques secondes...")
            await bot.send_message(ADMIN_ID, f"💰 Nouveau paiement de {montant}€ de {message.from_user.username or message.from_user.first_name}. N'oublie pas d'envoyer son média.")
            log_to_airtable(
                pseudo=message.from_user.username or message.from_user.first_name,
                user_id=message.from_user.id,
                type_acces="Paiement",
                montant=float(montant),
                contenu="Paiement Contenu"
            )
            await bot.send_message(ADMIN_ID, "✅ Paiement enregistré dans ton Dashboard.")
            return
        else:
            paiements_en_attente_par_user.add(user_id)
    if param in ["vipcdan"]:
        authorized_users.add(message.from_user.id)
        await bot.send_message(message.chat.id, "✨ Bienvenue dans le VIP ! Tu peux désormais m'écrire ici...💕")
        await bot.send_message(ADMIN_ID, f"🌟 Nouveau VIP : {message.from_user.username or message.from_user.first_name}.")
        log_to_airtable(
    pseudo=message.from_user.username or message.from_user.first_name,
    user_id=message.from_user.id,
    type_acces="VIP",
    montant= 1.0,
    contenu="Accès VIP Telegram"
)

        await bot.send_message(ADMIN_ID, "✅ VIP Access enregistré dans ton dashboard.")
        return
# Message perso à l'admin
    if message.from_user.id == ADMIN_ID:
        await bot.send_message(message.chat.id, "👋 Bonjour admin ! Tu peux voir le listing des différentes commandes pour ne pas te tromper et consulter tes statistiques !", reply_markup=keyboard_admin)
    else:
        await bot.send_message(message.chat.id, f"👋 Coucou {message.from_user.first_name or 'toi'}, que veux-tu faire 💕 ?", reply_markup=keyboard)

# Gestion des boutons

@dp.message_handler(lambda message: message.text == "✨Discuter en tant que VIP")
async def discuter_vip(message: types.Message):
    await bot.send_message(message.chat.id, "🚀 Deviens VIP ici : https://buy.stripe.com/4gwg32fhF4K62fCdQR")

@dp.message_handler(lambda message: message.text == "👀Je suis un voyeur")
async def je_suis_voyeur(message: types.Message):
    keyboard_confirm = types.ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard_confirm.add(
        types.KeyboardButton("❌ Oui je confirme (bannir)"),
        types.KeyboardButton("✅ Non, je veux rejoindre le VIP")
    )
    await bot.send_message(message.chat.id, "Confirme ton choix :", reply_markup=keyboard_confirm)

@dp.message_handler(lambda message: message.text == "❌ Oui je confirme (bannir)")
async def confirmer_voyeur(message: types.Message):
    await bot.send_message(message.chat.id, "🛑 Tu restes simple spectateur.")

@dp.message_handler(lambda message: message.text == "✅ Non, je veux rejoindre le VIP")
async def rejoindre_vip(message: types.Message):
    await bot.send_message(message.chat.id, "✅ Super ! Voici ton lien VIP : https://buy.stripe.com/4gwg32fhF4K62fCdQR", reply_markup=keyboard)

# Message avec lien

import re

@dp.message_handler(
    lambda message: message.from_user.id == ADMIN_ID and (
        (message.text and "/env" in message.text) or 
        (message.caption and "/env" in message.caption)
    ),
    content_types=[types.ContentType.TEXT, types.ContentType.PHOTO, types.ContentType.VIDEO, types.ContentType.DOCUMENT]
)
async def envoyer_lien_stripe(message: types.Message):
    if not message.reply_to_message:
        await bot.send_message(chat_id=ADMIN_ID, text="❗ Utilise la commande en réponse à un message du client.")
        return

    user_id = None
    if message.reply_to_message.forward_from:
        user_id = message.reply_to_message.forward_from.id
    else:
        user_id = pending_replies.get((message.chat.id, message.reply_to_message.message_id))

    if not user_id:
        await bot.send_message(chat_id=ADMIN_ID, text="❗ Impossible d'identifier le destinataire.")
        return
# 22 Mettre les liens propres à l'admin
    liens_paiement = {
        "9": "https://buy.stripe.com/fZeg328Th4K67zW9AA",
        "14": "https://buy.stripe.com/aEUeYYd9xfoKaM8bIL",
        "19": "https://buy.stripe.com/5kAaIId9x90mbQc148",
        "24": "https://buy.stripe.com/...",
        "29": "https://buy.stripe.com/...",
        "34": "https://buy.stripe.com/...",
        "39": "https://buy.stripe.com/...",
        "49": "https://buy.stripe.com/...",
        "59": "https://buy.stripe.com/...",
        "69": "https://buy.stripe.com/...",
        "79": "https://buy.stripe.com/...",
        "89": "https://buy.stripe.com/...",
        "99": "https://buy.stripe.com/...",
    }

    texte = message.caption or message.text or ""
    match = re.search(r"/env(\d+|vip)", texte.lower())
    if not match:
        await bot.send_message(chat_id=ADMIN_ID, text="❗ Aucun code /envXX valide détecté.")
        return

    code = match.group(1)
    lien = liens_paiement.get(code)
    if not lien:
        await bot.send_message(chat_id=ADMIN_ID, text="❗ Ce montant n'est pas reconnu dans les liens disponibles.")
        return

    nouvelle_legende = re.sub(r"/env(\d+|vip)", f"{lien}", texte)

    if not (message.photo or message.video or message.document):
        await bot.send_photo(chat_id=user_id, photo=DEFAULT_FLOU_IMAGE_FILE_ID, caption=nouvelle_legende)
        await bot.send_message(
    chat_id=user_id,
    text=f"_🔒 Ce contenu à {code} € est verrouillé. Clique sur le lien ci-dessus pour le débloquer._",
    parse_mode="Markdown"
)


        return

    if message.content_type == types.ContentType.PHOTO:
        await bot.send_photo(chat_id=user_id, photo=message.photo[-1].file_id, caption=nouvelle_legende)
    elif message.content_type == types.ContentType.VIDEO:
        await bot.send_video(chat_id=user_id, video=message.video.file_id, caption=nouvelle_legende)
    elif message.content_type == types.ContentType.DOCUMENT:
        await bot.send_document(chat_id=user_id, document=message.document.file_id, caption=nouvelle_legende)
    else:
        await bot.send_message(chat_id=user_id, text=nouvelle_legende, disable_web_page_preview=True)

# Stocker le média personnalisé en réponse avec /dev ===
@dp.message_handler(lambda m: m.from_user.id == ADMIN_ID and (
    (m.caption and "/dev" in m.caption.lower()) or 
    (m.text and "/dev" in m.text.lower())
), content_types=types.ContentType.ANY)
async def stocker_media_par_user(message: types.Message):
    if not message.reply_to_message:
        await bot.send_message(chat_id=ADMIN_ID, text="❗ Utilise cette commande en réponse à un message client.")
        return

    user_id = None
    if message.reply_to_message.forward_from:
        user_id = message.reply_to_message.forward_from.id
    else:
        user_id = pending_replies.get((message.chat.id, message.reply_to_message.message_id))

    if not user_id:
        await bot.send_message(chat_id=ADMIN_ID, text="❗ Impossible d'identifier le destinataire.")
        return

    if not (message.photo or message.video or message.document):
        await bot.send_message(chat_id=ADMIN_ID, text="❗ Aucun média détecté.")
        return

    contenus_en_attente[user_id] = {
        "file_id": message.photo[-1].file_id if message.photo else message.video.file_id if message.video else message.document.file_id,
        "type": message.content_type,
        "caption": (message.caption or message.text or "").replace("/dev", "").strip()
    }

    await bot.send_message(chat_id=ADMIN_ID, text=f"✅ Contenu prêt pour l'utilisateur {user_id}.")

    # Si le client avait déjà payé → on lui envoie tout de suite
    if user_id in paiements_en_attente_par_user:
        contenu = contenus_en_attente[user_id]
        if contenu["type"] == types.ContentType.PHOTO:
            await bot.send_photo(chat_id=user_id, photo=contenu["file_id"], caption=contenu["caption"])
        elif contenu["type"] == types.ContentType.VIDEO:
            await bot.send_video(chat_id=user_id, video=contenu["file_id"], caption=contenu["caption"])
        elif contenu["type"] == types.ContentType.DOCUMENT:
            await bot.send_document(chat_id=user_id, document=contenu["file_id"], caption=contenu["caption"])
        paiements_en_attente_par_user.remove(user_id)
        del contenus_en_attente[user_id]   

# TEST VF debut
@dp.message_handler(lambda message: message.text == "📖 Commandes" and message.from_user.id == ADMIN_ID)
async def show_commandes_admin(message: types.Message):
    commandes = (
        "📖 *Liste des commandes disponibles :*\n\n"
        "📦 */dev* – Stocker un contenu\n"
        "_À utiliser en réponse à un message client. Joins un média (photo/vidéo) avec la commande dans la légende.Il sera placé en attente et se débloquera au moment où ton client aura payé._\n\n"
        "🔒 */envxx* – Envoyer un contenu payant €\n"
        "_Tape cette commande avec le bon montant (ex. /env14) pour envoyer un contenu flouté avec lien de paiement de 14 €. Ton client recevra directement une image floutée avec le lien de paiement._\n\n"
        "⚠️ ** – N'oublies pas de sélectionner le message du client à qui tu veux répondre\n"

        "⚠️ ** – Voici la liste des prix : 9, 14, 19, 24, 29, 34, 39, 44, 49, 59, 69, 79, 89, 99\n"

        "📬 *Besoin d’aide ?* Écris-moi par mail : novapulse.online@gmail.com"
    )
    await message.reply(commandes, parse_mode="Markdown")

@dp.message_handler(lambda message: message.text == "📊 Statistiques" and message.from_user.id == ADMIN_ID)
async def show_stats_direct(message: types.Message):
    await bot.send_message(message.chat.id, "📥 Traitement de tes statistiques de vente en cours...")

    try:
        url = f"https://api.airtable.com/v0/{BASE_ID}/{TABLE_NAME.replace(' ', '%20')}"
        headers = {
            "Authorization": f"Bearer {AIRTABLE_API_KEY}"
        }

        response = requests.get(url, headers=headers)
        data = response.json()

        ventes_totales = 0
        ventes_jour = 0
        contenus_vendus = 0
        emails_vip = set()

        today = datetime.now().date().isoformat()
        mois_courant = datetime.now().strftime("%Y-%m")


        for record in data.get("records", []):
            fields = record.get("fields", {})
            email = fields.get("Email", "")
            date_str = fields.get("Date", "")
            montant = float(fields.get("Montant", 0))
            type_acces = fields.get("Type acces", "")

            if email == SELLER_EMAIL and fields.get("Mois") == mois_courant:
                ventes_totales += montant
            if email == SELLER_EMAIL and date_str.startswith(today):
                ventes_jour += montant


                if type_acces.lower() != "vip":
                    contenus_vendus += 1

                if type_acces.lower() == "vip":
                    emails_vip.add(email)

        clients_vip = len(emails_vip)
        benefice_net = round(ventes_totales * 0.94, 2)

        message_final = (
            f"📊 Tes statistiques de vente :\n\n"
            f"💰 Ventes du jour : {ventes_jour}€\n"
            f"💶 Ventes totales : {ventes_totales}€\n"
            f"📦 Contenus vendus total : {contenus_vendus}\n"
            f"🌟 Clients VIP : {clients_vip}\n"
            f"📈 Bénéfice estimé net : {benefice_net}€\n\n"
            f"_Le bénéfice tient compte d’une commission de 6 %._"
        )

        await bot.send_message(message.chat.id, message_final, parse_mode="Markdown")

    except Exception as e:
        print(f"Erreur dans le bouton 📊 Statistiques : {e}")
        await bot.send_message(message.chat.id, "❌ Une erreur est survenue lors du traitement des statistiques.")


# --- Message relay (client -> admin & admin -> client) ---
pending_replies = {}
# === petite partie ajouté 
@dp.message_handler(lambda message: message.from_user.id != ADMIN_ID, content_types=types.ContentType.ANY)
async def relay_from_client(message: types.Message):
    if ADMIN_ID in ban_list and message.from_user.id in ban_list[ADMIN_ID]:
        print(f"❌ Message bloqué de {message.from_user.id} (banni)")
        return

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




