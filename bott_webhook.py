from core import bot, dp
from aiogram import types
import os
from datetime import datetime
from aiogram.dispatcher.handler import CancelHandler
import requests
from core import authorized_users
from detect_links_whitelist import lien_non_autorise
from collections import defaultdict
from datetime import datetime, timedelta
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


#banlist
ban_list = {}

# Dictionnaire temporaire pour stocker les derniers messages de chaque client
last_messages = {}
ADMIN_ID = 7334072965
authorized_admin_ids = [ADMIN_ID]



pending_mass_message = {}
admin_modes = {}  # Clé = admin_id, Valeur = "en_attente_message"

# Mapping entre ID Telegram des admins et leur email dans Airtable 19juillet 2025 debut
ADMIN_EMAILS = {
    7334072965: "vinteo.ac@gmail.com",
}
# Mapping entre ID Telegram des admins et leur email dans Airtable 19juillet 2025 fin


# Paiements validés par Stripe, stockés temporairement
paiements_recents = defaultdict(list)  # ex : {14: [datetime1, datetime2]}


# 1.=== Variables globales ===
DEFAULT_FLOU_IMAGE_FILE_ID = "AgACAgEAAxkBAAIOgWgSLV1I3pOt7vxnpci_ba-hb9UXAAK6rjEbM2KQRDdrQA-mqmNwAQADAgADeAADNgQ" # Remplace par le vrai file_id Telegram


# Fonction de détection de lien non autorisé
ALLOWED_DOMAINS = os.getenv("ALLOWED_DOMAINS", "").split(",")

# --- CONFIGURATION AIRTABLE ---
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

# === 221097 DEBUT

from core import authorized_users  # à mettre tout en haut si ce n’est pas déjà fait

def initialize_authorized_users():
    try:
        url = f"https://api.airtable.com/v0/{BASE_ID}/{TABLE_NAME.replace(' ', '%20')}"
        params = {"filterByFormula": "{Type acces}='VIP'"}
        headers = {"Authorization": f"Bearer {AIRTABLE_API_KEY}"}
        response = requests.get(url, headers=headers, params=params)
        response.raise_for_status()
        data = response.json()
        for record in data.get("records", []):
            telegram_id = record.get("fields", {}).get("ID Telegram")
            if telegram_id:
                try:
                    authorized_users.add(int(telegram_id))
                except ValueError:
                    print(f"[WARN] ID Telegram invalide : {telegram_id}")
        print(f"[INFO] {len(authorized_users)} utilisateurs VIP chargés depuis Airtable.")
    except Exception as e:
        print(f"[ERROR] Impossible de charger les VIP depuis Airtable : {e}")
# === 221097 FIN

# === Statistiques ===

@dp.message_handler(commands=["stat"])
async def handle_stat(message: types.Message):
    await bot.send_message(message.chat.id, "📥 Traitement de tes statistiques de vente en cours...")

    try:
        # --- FAUX CHIFFRES POUR DÉMO VIDÉO ---
        ventes_jour = 98
        ventes_totales = 4986
        contenus_vendus = 107
        clients_vip = 56
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

        vip_button = InlineKeyboardMarkup().add(
            InlineKeyboardButton("📋 Voir mes VIPs", callback_data="voir_mes_vips")
        )

        await bot.send_message(message.chat.id, message_final, parse_mode="Markdown", reply_markup=vip_button)

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
prix_list = [1, 9, 14, 19, 24, 29, 34, 39, 44, 49, 59, 69, 79, 89, 99]

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

def log_to_airtable(pseudo, user_id, type_acces, montant, contenu="Paiement Telegram", email="vinteo.ac@gmail.com",):
    if not type_acces:
        type_acces = "Paiement"  # Par défaut pour éviter erreurs

    url = f"https://api.airtable.com/v0/{BASE_ID}/{TABLE_NAME.replace(' ', '%20')}"
    headers = {
        "Authorization": f"Bearer {AIRTABLE_API_KEY}",
        "Content-Type": "application/json"
    }

    now = datetime.now()

    fields = {
        "Pseudo Telegram": pseudo or "-",
        "ID Telegram": str(user_id),
        "Type acces": str(type_acces),
        "Montant": float(montant),
        "Contenu": contenu,
        "Email": email,
        "Date": now.isoformat(),
        "Mois": now.strftime("%Y-%m")
    }

    data = {
        "fields": fields
    }

    try:
        response = requests.post(url, json=data, headers=headers)
        if response.status_code != 200:
            print(f"❌ Erreur Airtable : {response.text}")
        else:
            print("✅ Paiement ajouté dans Airtable avec succès !")
    except Exception as e:
        print(f"Erreur lors de l'envoi à Airtable : {e}")


# Création du clavier

keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
keyboard.add(
    types.KeyboardButton("👀Je suis un voyeur"),
    types.KeyboardButton("✨Discuter en tant que VIP"),
    types.KeyboardButton("❗ Problème achat")
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
keyboard_admin.add(
    types.KeyboardButton("✉️ Message à tous les VIPs")
)

keyboard.add(
    types.KeyboardButton("🔞 Voir le contenu du jour")
)

#Envoi du bouton du contenu du jour

@dp.message_handler(lambda message: message.text == "🔞 Voir le contenu du jour")
async def demande_contenu_jour(message: types.Message):
    # 1. Création du bouton avec le lien Stripe
    bouton_vip = InlineKeyboardMarkup().add(
        InlineKeyboardButton(
            text="🔥 Rejoindre le groupe VIP pour 1€",
            url="https://buy.stripe.com/4gwg32fhF4K62fCdQR"
        )
    )

    # 2. Envoi du message avec bouton intégré
    await message.reply(
        "✅ J'ai bien reçu ta demande !\n\n🚨 Mais le contenu du jour est réservé aux membres VIP.\n\nPour y accéder, clique sur le bouton ci-dessous 👇",
        reply_markup=bouton_vip
    )


    # 2. Le bot envoie une notif à l'admin avec le bouton "📋 Voir mes VIPs"
    vip_button = InlineKeyboardMarkup().add(
        InlineKeyboardButton("📋 Voir mes VIPs", callback_data="voir_mes_vips")
    )

    await bot.send_message(
        chat_id=ADMIN_ID,
        text=f"📥 Nouvelle demande de contenu du jour reçue ! \n\nVérifie bien qu'il soit VIP avant d'envoyer le contenu.",
        reply_markup=vip_button
    )

    forwarded = await bot.forward_message(
        chat_id=ADMIN_ID,
        from_chat_id=message.chat.id,
        message_id=message.message_id
    )

    pending_replies[(forwarded.chat.id, forwarded.message_id)] = message.chat.id


#fin de l'envoi du bouton du contenu du jour



# Détecter le paiement /start=cdan... et envoyer si contenu déjà prêt ===
@dp.message_handler(commands=["start"])
async def handle_start(message: types.Message):
    param = message.get_args()
    user_id = message.from_user.id

    # Cas 1 : Paiement avec /start=cdanXX
    if param.startswith("cdan") and param[4:].isdigit():
        montant = int(param[4:])
        if montant in prix_list:
            now = datetime.now()
            paiements_valides = [
                t for t in paiements_recents.get(montant, [])
                if now - t < timedelta(minutes=3)
            ]

            if not paiements_valides:
                await bot.send_message(user_id, "❌ Paiement non valide ! Stripe a refusé votre paiement car fonds insuffisants ou refus général. Vérifie tes capacités de paiement.")
                await bot.send_message(ADMIN_ID, f"⚠️ Problème ! Stripe a refusé le paiement de ton client {message.from_user.username or message.from_user.first_name}.")
                return

            # Paiement validé
            paiements_recents[montant].remove(paiements_valides[0])
            authorized_users.add(user_id)

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

            await bot.send_message(user_id,
                f"✅ Merci pour ton paiement de {montant}€ 💖 ! Ton contenu arrive dans quelques secondes...\n\n"
                f"_❗️En cas de problème avec ta commande, contacte-nous à novapulse.online@gmail.com_",
                parse_mode="Markdown"
            )

            await bot.send_message(ADMIN_ID, f"💰 Nouveau paiement de {montant}€ de {message.from_user.username or message.from_user.first_name}.")
            log_to_airtable(
                pseudo=message.from_user.username or message.from_user.first_name,
                user_id=user_id,
                type_acces="Paiement",
                montant=float(montant),
                contenu="Paiement validé via Stripe webhook + redirection"
            )
            await bot.send_message(ADMIN_ID, "✅ Paiement enregistré dans ton Dashboard.")
            return
        else:
            await bot.send_message(user_id, "❌ Le montant indiqué n’est pas valide.")
            return

    # Cas 2 : VIP avec /start=vipcdan
    elif param == "vipcdan":
        authorized_users.add(user_id)
        await bot.send_message(user_id, "✨ Bienvenue dans le VIP ! Tu peux désormais m'écrire ici...💕")
        await bot.send_message(ADMIN_ID, f"🌟 Nouveau VIP : {message.from_user.username or message.from_user.first_name}.")
        log_to_airtable(
            pseudo=message.from_user.username or message.from_user.first_name,
            user_id=user_id,
            type_acces="VIP",
            montant=1.0,
            contenu="Accès VIP Telegram"
        )
        await bot.send_message(ADMIN_ID, "✅ VIP Access enregistré dans ton dashboard.")
        return

    # Cas 3 : Accès normal
    if user_id == ADMIN_ID:
        await bot.send_message(user_id, "👋 Bonjour admin ! Tu peux voir le listing des commandes et consulter tes statistiques !", reply_markup=keyboard_admin)
    else:
        await bot.send_message(user_id, f"👋 Coucou {message.from_user.first_name or 'toi'}, que veux-tu faire 💕 ?", reply_markup=keyboard)

# Gestion des boutons

@dp.message_handler(lambda message: message.text == "✨Discuter en tant que VIP")
async def discuter_vip(message: types.Message):
    bouton_vip = InlineKeyboardMarkup().add(
        InlineKeyboardButton(
            text="💬 Devenir VIP pour 1€",
            url="https://buy.stripe.com/4gwg32fhF4K62fCdQR"
        )
    )

    await bot.send_message(
        message.chat.id,
        "🚀 Deviens VIP pour débloquer l'accès à la discussion privée, au contenu exclusif et aux surprises réservées aux membres !\n\nClique ici 👇",
        reply_markup=bouton_vip
    )

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


 # TEST
@dp.message_handler(lambda message: message.text == "❗ Problème achat")
async def probleme_achat(message: types.Message):
    texte_client = (
        "❗ *Un souci avec ton achat ?*\n\n"
        "Pas de panique ! Nous prenons très au sérieux chaque cas. "
        "Tu peux nous écrire directement à *novapulse.online@gmail.com* avec ton pseudo Telegram, "
        "et on investiguera ta situation dès maintenant !\n\n"
        "_Ne dépose pas de litige sur Stripe car nous allons nous occuper de la situtation._"
    )
    await bot.send_message(message.chat.id, texte_client, parse_mode="Markdown")

    pseudo = message.from_user.username or message.from_user.first_name or "Inconnu"
    user_id = message.from_user.id

    # 🔔 Alerte pour le vendeur (admin)
    await bot.send_message(ADMIN_ID,
        f"⚠️ *ALERTE LITIGE CLIENT* :\n\n"
        f"Le client {pseudo} (ID: {user_id}) a cliqué sur *'Problème achat'*.\n"
        f"Pense à vérifier si tout est OK.",
        parse_mode="Markdown"
    )

    # 🔔 Alerte pour le directeur
    await bot.send_message(DIRECTEUR_ID,
        f"🔔 *Problème achat détecté*\n\n"
        f"👤 Client : {pseudo} (ID: {user_id})\n"
        f"👨‍💼 Admin concerné : {ADMIN_ID}",
        parse_mode="Markdown"
    )

    print(f"✅ Alertes envoyées à ADMIN_ID ({ADMIN_ID}) et DIRECTEUR_ID ({DIRECTEUR_ID})")

# TEST FIN


    # Envoi à l'admin (vendeur)
    try:
        await bot.send_message(ADMIN_ID, texte_alerte_admin, parse_mode="Markdown")
    except Exception as e:
        print(f"Erreur envoi admin : {e}")

    # Envoi au directeur (toi)
    try:
        await bot.send_message(DIRECTEUR_ID, texte_alerte_directeur, parse_mode="Markdown")
    except Exception as e:
        print(f"Erreur envoi directeur : {e}")


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
        "1": "https://buy.stripe.com/00g5ooedBfoK07u6oE",
        "9": "https://buy.stripe.com/fZeg328Th4K67zW9AA",
        "14": "https://buy.stripe.com/aEUeYYd9xfoKaM8bIL",
        "19": "https://buy.stripe.com/5kAaIId9x90mbQc148",
        "24": "https://buy.stripe.com/7sI2cc0mL90m2fC3ch",
        "29": "https://buy.stripe.com/9AQcQQ5H5gsOdYkeV0",
        "34": "https://buy.stripe.com/6oE044d9x90m5rOcMT",
        "39": "https://buy.stripe.com/fZe8AA6L990m8E07sA",
        "49": "https://buy.stripe.com/9AQ6ss0mL7Wi2fCdR0",
        "59": "https://buy.stripe.com/3csdUUfhFdgC6vS7sD",
        "69": "https://buy.stripe.com/cN21880mLb8udYk00c",
        "79": "https://buy.stripe.com/6oE8AA1qPccyf2o28l",
        "89": "https://buy.stripe.com/5kAeYYglJekG2fC7sG",
        "99": "https://buy.stripe.com/cN26ss0mL90m3jG4gv",
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
    await handle_stat(message)

# test du résume du dernier message recu 
@dp.message_handler(lambda message: message.chat.id not in authorized_admin_ids)
async def handle_admin_message(message: types.Message):
    user_id = message.from_user.id

    def escape_html(text):
        if not text:
            return "[Message vide]"
        return (
            text.replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
        )

    new_msg = escape_html(message.text)
    old_msg = escape_html(last_messages.get(user_id, "Aucun message"))

    last_messages[user_id] = message.text or "[Message vide]"

    await bot.forward_message(ADMIN_ID, user_id, message.message_id)

    response = (
        f"🗨️ <b>Dernier message :</b>\n{old_msg}\n\n"
        f"🆕 <b>Nouveau :</b>\n{new_msg}"
    )

    await bot.send_message(ADMIN_ID, response, parse_mode="HTML")


# fin du resume du dernier message recu 

# ======================== IMPORTS & VARIABLES ========================

# ========== IMPORTS ESSENTIELS ==========
from aiogram import types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# ========== HANDLER CLIENT : transfert vers admin ==========

@dp.message_handler(lambda message: message.from_user.id != ADMIN_ID, content_types=types.ContentType.ANY)
async def relay_from_client(message: types.Message):
    user_id = message.from_user.id

    # ✅ Vérifie si le client est banni
    if user_id in ban_list.get(ADMIN_ID, set()):
        print(f"⛔ Message bloqué de {user_id} (banni)")
        return  # Le message ne sera pas transféré

    try:
        sent_msg = await bot.forward_message(chat_id=ADMIN_ID, from_chat_id=user_id, message_id=message.message_id)
        pending_replies[(sent_msg.chat.id, sent_msg.message_id)] = user_id
        print(f"✅ Message reçu de {user_id} et transféré à l'admin")
    except Exception as e:
        print(f"❌ Erreur transfert message client : {e}")


# ========== HANDLER ADMIN : réponses privées + messages groupés ==========

@dp.message_handler(lambda message: message.from_user.id == ADMIN_ID, content_types=types.ContentType.ANY)
async def handle_admin_message(message: types.Message):
    mode = admin_modes.get(ADMIN_ID)

    # ✅ Si l'admin clique sur "Message à tous les VIPs"
    if message.text == "✉️ Message à tous les VIPs":
        admin_modes[ADMIN_ID] = "en_attente_message"
        await bot.send_message(chat_id=ADMIN_ID, text="✍️ Quel message veux-tu envoyer à tous les VIPs ?")
        return

    # ✅ Si l'admin est en mode groupé, on traite le contenu du message
    if mode == "en_attente_message":
        admin_modes[ADMIN_ID] = None
        await traiter_message_groupé(message)
        return

    # ✅ Sinon, on attend un reply pour une réponse privée
    if not message.reply_to_message:
        print("❌ Pas de reply détecté (et pas en mode groupé)")
        return

    # 🔍 Identification du destinataire
    user_id = None
    if message.reply_to_message.forward_from:
        user_id = message.reply_to_message.forward_from.id
    else:
        user_id = pending_replies.get((message.chat.id, message.reply_to_message.message_id))

    if not user_id:
        await bot.send_message(chat_id=ADMIN_ID, text="❗Impossible d'identifier le destinataire.")
        return

    # ✅ Envoi de la réponse
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
            await bot.send_message(chat_id=ADMIN_ID, text="📂 Type de message non supporté.")
    except Exception as e:
        await bot.send_message(chat_id=ADMIN_ID, text=f"❗Erreur admin -> client : {e}")

# ========== TRAITEMENT MESSAGE GROUPÉ VIPs ==========

async def traiter_message_groupé(message: types.Message):
    if message.text:
        pending_mass_message[ADMIN_ID] = {"type": "text", "content": message.text}
        preview = message.text
    elif message.photo:
        pending_mass_message[ADMIN_ID] = {"type": "photo", "content": message.photo[-1].file_id, "caption": message.caption or ""}
        preview = f"[Photo] {message.caption or ''}"
    elif message.video:
        pending_mass_message[ADMIN_ID] = {"type": "video", "content": message.video.file_id, "caption": message.caption or ""}
        preview = f"[Vidéo] {message.caption or ''}"
    elif message.audio:
        pending_mass_message[ADMIN_ID] = {"type": "audio", "content": message.audio.file_id, "caption": message.caption or ""}
        preview = f"[Audio] {message.caption or ''}"
    elif message.voice:
        pending_mass_message[ADMIN_ID] = {"type": "voice", "content": message.voice.file_id}
        preview = "[Note vocale]"
    else:
        await message.reply("❌ Message non supporté.")
        return

    confirmation = InlineKeyboardMarkup(row_width=2)
    confirmation.add(
        InlineKeyboardButton("✅ Confirmer l’envoi", callback_data="confirmer_envoi_groupé"),
        InlineKeyboardButton("❌ Annuler l’envoi", callback_data="annuler_envoi_groupé")
    )

    await message.reply(f"Prévisualisation :\n\n{preview}", reply_markup=confirmation)

# ========== CALLBACKS ENVOI / ANNULATION GROUPÉ ==========

@dp.callback_query_handler(lambda call: call.data == "confirmer_envoi_groupé")
async def confirmer_envoi_groupé(call: types.CallbackQuery):
    await call.answer()
    message_data = pending_mass_message.get(ADMIN_ID)
    if not message_data:
        await call.message.edit_text("❌ Aucun message en attente à envoyer.")
        return

    await call.message.edit_text("⏳ Envoi du message à tous les VIPs...")
    envoyes = 0
    erreurs = 0

    for vip_id in authorized_users:
        try:
            if message_data["type"] == "text":
                await bot.send_message(chat_id=int(vip_id), text=message_data["content"])
            elif message_data["type"] == "photo":
                await bot.send_photo(chat_id=int(vip_id), photo=message_data["content"], caption=message_data.get("caption", ""))
            elif message_data["type"] == "video":
                await bot.send_video(chat_id=int(vip_id), video=message_data["content"], caption=message_data.get("caption", ""))
            elif message_data["type"] == "audio":
                await bot.send_audio(chat_id=int(vip_id), audio=message_data["content"], caption=message_data.get("caption", ""))
            elif message_data["type"] == "voice":
                await bot.send_voice(chat_id=int(vip_id), voice=message_data["content"])
            envoyes += 1
        except Exception as e:
            print(f"❌ Erreur envoi à {vip_id} : {e}")
            erreurs += 1

    await bot.send_message(chat_id=ADMIN_ID, text=f"✅ Envoyé à {envoyes} VIP(s).\n⚠️ Échecs : {erreurs}")
    pending_mass_message.pop(ADMIN_ID, None)

@dp.callback_query_handler(lambda call: call.data == "annuler_envoi_groupé")
async def annuler_envoi_groupé(call: types.CallbackQuery):
    await call.answer("❌ Envoi annulé.")
    pending_mass_message.pop(ADMIN_ID, None)
    await call.message.edit_text("❌ Envoi annulé.")

#debut du 19 juillet 2025 mettre le tableau de vips
@dp.callback_query_handler(lambda c: c.data == "voir_mes_vips")
async def voir_mes_vips(callback_query: types.CallbackQuery):
    telegram_id = callback_query.from_user.id
    email = ADMIN_EMAILS.get(telegram_id)

    if not email:
        await bot.send_message(telegram_id, "❌ Ton e-mail admin n’est pas reconnu.")
        return

    await callback_query.answer("Chargement de tes VIPs...")

    headers = {
        "Authorization": f"Bearer {os.getenv('AIRTABLE_API_KEY')}"
    }

    url = "https://api.airtable.com/v0/appdA5tvdjXiktFzq/tblwdps52XKMk43xo"
    params = {
        "filterByFormula": f"{{Email}} = '{email}'"
    }

    response = requests.get(url, headers=headers, params=params)
    if response.status_code != 200:
        await bot.send_message(telegram_id, f"❌ Erreur Airtable : {response.status_code}\n\n{response.text}")
        return

    records = response.json().get("records", [])
    if not records:
        await bot.send_message(telegram_id, "📭 Aucun enregistrement trouvé pour toi.")
        return

    # Étape 1 : repérer les pseudos ayant AU MOINS une ligne Type acces = VIP
    pseudos_vip = set()
    for r in records:
        f = r.get("fields", {})
        pseudo = f.get("Pseudo Telegram", "").strip()
        type_acces = f.get("Type acces", "").strip().lower()
        if pseudo and type_acces == "vip":
            pseudos_vip.add(pseudo)

    # Étape 2 : additionner TOUS les montants (Paiement + VIP) de ces pseudos uniquement
    montants_par_pseudo = {}
    for r in records:
        f = r.get("fields", {})
        pseudo = f.get("Pseudo Telegram", "").strip()
        montant = f.get("Montant")

        if not pseudo or pseudo not in pseudos_vip:
            continue

        try:
            montant_float = float(montant)
        except:
            montant_float = 0.0

        if pseudo not in montants_par_pseudo:
            montants_par_pseudo[pseudo] = 0.0

        montants_par_pseudo[pseudo] += montant_float

    try:
        # Construction du message final avec tri et top 3
        message = "📋 Voici tes clients VIP (avec tous leurs paiements) :\n\n"
        sorted_vips = sorted(montants_par_pseudo.items(), key=lambda x: x[1], reverse=True)

        for pseudo, total in sorted_vips:
            message += f"👤 @{pseudo} — {round(total)} €\n"

        # 🏆 Top 3
        top3 = sorted_vips[:3]
        if top3:
            message += "\n🏆 *Top 3 clients :*\n"
            for i, (pseudo, total) in enumerate(top3):
                place = ["🥇", "🥈", "🥉"]
                emoji = place[i] if i < len(place) else f"#{i+1}"
                message += f"{emoji} @{pseudo} — {round(total)} €\n"

        await bot.send_message(telegram_id, message)

    except Exception as e:
        import traceback
        error_text = traceback.format_exc()
        print("❌ ERREUR DANS VIPS + TOP 3 :\n", error_text)
        await bot.send_message(telegram_id, "❌ Une erreur est survenue lors de l'affichage des VIPs.")

#fin du 19 juillet 2025 mettre le tableau de vips








