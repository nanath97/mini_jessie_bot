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
from ban_storage import ban_list




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
    await bot.send_message(message.chat.id, "📥 Procesamiento de tus estadísticas de ventas actuales...")

    try:
        # --- FAUX CHIFFRES POUR DÉMO VIDÉO ---
        ventes_jour = 98
        ventes_totales = 4986
        contenus_vendus = 107
        clients_vip = 56
        benefice_net = round(ventes_totales * 0.94, 2)

        message_final = (
            f"📊 Tus estadísticas de ventas :\n\n"
            f"💰 Ventas del día : {ventes_jour}€\n"
            f"💶 Ventas totales : {ventes_totales}€\n"
            f"📦 Total de contenidos vendidos : {contenus_vendus}\n"
            f"🌟 Clientes VIP : {clients_vip}\n"
            f"📈 Beneficio neto estimado : {benefice_net}€\n\n"
            f"_La ganancia incluye una comisión del 6 %._"
        )

        vip_button = InlineKeyboardMarkup().add(
            InlineKeyboardButton("📋 Ver mis VIP", callback_data="ver_mis_vips")
        )

        await bot.send_message(message.chat.id, message_final, parse_mode="Markdown", reply_markup=vip_button)

    except Exception as e:
        print(f"Erreur dans /stat : {e}")
        await bot.send_message(message.chat.id, "❌ Se ha producido un error al recuperar las estadísticas.")


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
@dp.message_handler(commands=['supp'])
async def bannir_client(message: types.Message):
    if not message.reply_to_message:
        await message.reply("❌ Utilice este comando en respuesta al mensaje del cliente para retirar.")
        return

    user_id = None
    if message.reply_to_message.forward_from:
        user_id = message.reply_to_message.forward_from.id
    else:
        user_id = pending_replies.get((message.chat.id, message.reply_to_message.message_id))

    if not user_id:
        await message.reply("❌ No se puede identificar al cliente. Responde correctamente a un mensaje reenviado por el bot.")
        return

    admin_id = message.from_user.id

    if admin_id not in ban_list:
        ban_list[admin_id] = []

    if user_id not in ban_list[admin_id]:
        ban_list[admin_id].append(user_id)

        await message.reply("✅ El cliente se ha eliminado correctamente.")
        try:
            await bot.send_message(user_id, "❌ Lo sentimos, pero ha sido eliminado del grupo VIP.")
        except Exception as e:
            print(f"Erreur lors de l'envoi du message au client banni : {e}")
            await message.reply("ℹ️ Le client est bien banni, mais je n’ai pas pu lui envoyer le message (permissions Telegram).")
    else:
        await message.reply("ℹ️ Este cliente ya se ha retirado.")


@dp.message_handler(commands=['unsupp'])
async def reintegrer_client(message: types.Message):
    if not message.reply_to_message:
        await message.reply("❌ Utilice este comando en respuesta al mensaje del cliente que desea reintegrar.")
        return

    user_id = None
    if message.reply_to_message.forward_from:
        user_id = message.reply_to_message.forward_from.id
    else:
        user_id = pending_replies.get((message.chat.id, message.reply_to_message.message_id))

    if not user_id:
        await message.reply("❌ No se puede identificar al cliente. Responde correctamente a un mensaje reenviado por el bot.")
        return

    admin_id = message.from_user.id

    if admin_id in ban_list and user_id in ban_list[admin_id]:
        ban_list[admin_id].remove(user_id)

        await message.reply("✅ El cliente ha sido reintegrado con éxito.")
        try:
            await bot.send_message(user_id, "✅ Ha sido readmitido en el grupo VIP !")
        except Exception as e:
            print(f"Erreur lors de l'envoi du message au client réintégré : {e}")
            await message.reply("ℹ️ Réintégré, mais le message n’a pas pu être envoyé (permissions Telegram).")

    else:
        await message.reply("ℹ️ Ce client n’était pas retiré.")

# Mise sous forme de boutons : bannissement

@dp.message_handler(lambda message: message.text == "❌ Expulsar al cliente" and message.reply_to_message and message.from_user.id == ADMIN_ID)
async def bouton_bannir(message: types.Message):
    forwarded = message.reply_to_message.forward_from
    if not forwarded:
        await message.reply("❌ Debes responder a un mensaje reenviado por el cliente.")
        return

    user_id = forwarded.id
    ban_list.setdefault(message.from_user.id, set()).add(user_id)
    await message.reply(f"🚫 El cliente ha sido expulsado correctamente.")
    try:
        await bot.send_message(user_id, "❌ Has sido eliminado. Ya no puedes volver a contactarme.")
    except Exception as e:
        print(f"Erreur d'envoi au client banni : {e}")
        await message.reply("ℹ️ Le client est banni, mais je n’ai pas pu lui envoyer le message.")


@dp.message_handler(lambda message: message.text == "✅ Reintegrar al cliente" and message.reply_to_message and message.from_user.id == ADMIN_ID)
async def bouton_reintegrer(message: types.Message):
    forwarded = message.reply_to_message.forward_from
    if not forwarded:
        await message.reply("❌ Debes responder a un mensaje reenviado por el cliente.")
        return

    user_id = forwarded.id
    if user_id in ban_list.get(message.from_user.id, set()):
        ban_list[message.from_user.id].remove(user_id)
        await message.reply(f"✅ El cliente ha sido reintegrado.")
        try:
            await bot.send_message(user_id, "✅ Has sido readmitido, puedes volver a ponerte en contacto conmigo.")
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
            await bot.send_message(chat_id=message.chat.id, text="🚫 Los enlaces externos están prohibidos.")
            
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
            print("✅ Pago agregado correctamente en Airtable !")
    except Exception as e:
        print(f"Erreur lors de l'envoi à Airtable : {e}")


# Création du clavier

keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
keyboard.add(
    types.KeyboardButton("👀Soy un mirón."),
    types.KeyboardButton("✨Chatear como VIP"),
    types.KeyboardButton("❗ Problema con la compra")
)
keyboard_admin = types.ReplyKeyboardMarkup(resize_keyboard=True)
keyboard_admin.add(
    types.KeyboardButton("📖 Pedidos"),
    types.KeyboardButton("📊 Estadísticas")
)
keyboard_admin.add(# TEST bouton admin
    types.KeyboardButton("❌ Expulsar al cliente"),
    types.KeyboardButton("✅ Reintegrar al cliente")
)
keyboard_admin.add(
    types.KeyboardButton("✉️ Mensaje para todos los VIP")
)

keyboard.add(
    types.KeyboardButton("🔞 Ver el contenido del día")
)

@dp.message_handler(lambda message: message.text == "🔞 Ver el contenido del día")
async def demande_contenu_jour(message: types.Message):
    user_id = message.from_user.id

    if user_id not in authorized_users:
        bouton_vip = InlineKeyboardMarkup().add(
            InlineKeyboardButton(
                text="🔥 Únete al grupo VIP por 1 €",
                url="https://buy.stripe.com/4gwg32fhF4K62fCdQR"
            )
        )

        await message.reply(
            "✅ He recibido tu solicitud !\n\n🚨 Pero el contenido de hoy está reservado para los miembros VIP.\n\nPara acceder, haz clic en el botón de abajo. 👇\n\n<i>🔐 Pago seguro mediante Stripe</i>",
            reply_markup=bouton_vip,
            parse_mode="HTML"
        )
        return  # Stop ici si ce n’est pas un VIP

    # ✅ Réponse automatique au VIP
    await message.reply("👀 Hola, te enviaré el contenido del día en un momento… 🔞")

    # ✅ Notification pour l’admin
    await bot.send_message(
        chat_id=ADMIN_ID,
        text=f"📥 Nueva solicitud de contenido del día recibida de un VIP !"
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
                await bot.send_message(user_id, "❌ Pago no válido! Stripe ha rechazado tu pago por fondos insuficientes o rechazo general. Comprueba tu capacidad de pago.")
                await bot.send_message(ADMIN_ID, f"⚠️ Problema ! Stripe ha rechazado el pago de tu cliente {message.from_user.username or message.from_user.first_name}.")
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
                f"✅ Gracias por tu pago de {montant}€ 💖 ! Tu contenido llegará en unos segundos...\n\n"
                f"_❗️Si tienes algún problema con tu pedido, contáctanos en novapulse.online@gmail.com_",
                parse_mode="Markdown"
            )

            await bot.send_message(ADMIN_ID, f"💰 Nuevo pago de {montant}€ de {message.from_user.username or message.from_user.first_name}.")
            log_to_airtable(
                pseudo=message.from_user.username or message.from_user.first_name,
                user_id=user_id,
                type_acces="Paiement",
                montant=float(montant),
                contenu="Paiement validé via Stripe webhook + redirection"
            )
            await bot.send_message(ADMIN_ID, "✅ Pago registrado en tu panel de control.")
            return
        else:
            await bot.send_message(user_id, "❌ El importe indicado no es válido.")
            return

    # Cas 2 : VIP avec /start=vipcdan
    elif param == "vipcdan":
        authorized_users.add(user_id)
        await bot.send_message(user_id, "✨ Bienvenido al VIP! Ahora puedes escribirme o incluso ver el contenido del día...💕")
        await bot.send_message(ADMIN_ID, f"🌟 Nuevo VIP : {message.from_user.username or message.from_user.first_name}.")
        log_to_airtable(
            pseudo=message.from_user.username or message.from_user.first_name,
            user_id=user_id,
            type_acces="VIP",
            montant=1.0,
            contenu="Accès VIP Telegram"
        )
        await bot.send_message(ADMIN_ID, "✅ Acceso VIP registrado en tu panel de control.")
        return
    
    # Ton file_id audio (change-le pour chaque instance client)
    WELCOME_AUDIO_FILE_ID = "CQACAgQAAxkBAAIxM2iI3QSy6f1bs63rscmdcvv29usSAAKeGAACyR9IUDNlXhtBM21INgQ"

    if user_id == ADMIN_ID:
        await bot.send_message(user_id, "👋 Hola, administrador ! Puedes ver la lista de pedidos y consultar tus estadísticas !", reply_markup=keyboard_admin)
    else:
        await bot.send_message(user_id, f"👋 Hola {message.from_user.first_name or 'toi'}, Qué quieres hacer 💕 ?", reply_markup=keyboard)   

    # 🔊 Audio juste après le message d’accueil
    await bot.send_voice(
        user_id,
        voice=WELCOME_AUDIO_FILE_ID
    )

# Gestion des boutons…


@dp.message_handler(lambda message: message.text == "✨Chatear como VIP")
async def discuter_vip(message: types.Message):
    bouton_vip = InlineKeyboardMarkup().add(
        InlineKeyboardButton(
            text="💬 Conviértete en VIP por 1 €",
            url="https://buy.stripe.com/4gwg32fhF4K62fCdQR"
        )
    )

    await bot.send_message(
    message.chat.id,
    "🚀 Hazte VIP para desbloquear el acceso al chat privado, contenido exclusivo y sorpresas reservadas para los miembros !\n\nHaz clic aquí 👇\n\n<i>🔐 Pago seguro con Stripe</i>",
    reply_markup=bouton_vip,
    parse_mode="HTML"
)


@dp.message_handler(lambda message: message.text == "👀Soy un mirón")
async def je_suis_voyeur(message: types.Message):
    keyboard_confirm = types.ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard_confirm.add(
        types.KeyboardButton("❌ Sí, lo confirmo (prohibido)"),
        types.KeyboardButton("✅ No, quiero unirme al VIP")
    )
    await bot.send_message(message.chat.id, "Confirma tu elección :", reply_markup=keyboard_confirm)

@dp.message_handler(lambda message: message.text == "❌ Sí, lo confirmo (prohibido)")
async def confirmer_voyeur(message: types.Message):
    await bot.send_message(message.chat.id, "🛑 Te quedas como simple espectador.")

@dp.message_handler(lambda message: message.text == "✅ No, quiero unirme al VIP")
async def rejoindre_vip(message: types.Message):
    await bot.send_message(message.chat.id, "✅ Genial ! Aquí tienes tu enlace VIP : https://buy.stripe.com/4gwg32fhF4K62fCdQR", reply_markup=keyboard)


 # TEST
@dp.message_handler(lambda message: message.text == "❗ Problema con la compra")
async def probleme_achat(message: types.Message):
    texte_client = (
        "❗ *Algún problema con tu compra ?*\n\n"
        "No se preocupe! Nos tomamos muy en serio cada caso. "
        "Puedes escribirnos directamente a *novapulse.online@gmail.com* con tu nombre de usuario de Telegram, "
        "y vamos a investigar tu situación de inmediato !\n\n"
        "_No presentes ninguna reclamación en Stripe, ya que nosotros nos encargaremos de la situación._"
    )
    await bot.send_message(message.chat.id, texte_client, parse_mode="Markdown")

    pseudo = message.from_user.username or message.from_user.first_name or "Inconnu"
    user_id = message.from_user.id

    # 🔔 Alerte pour le vendeur (admin)
    await bot.send_message(ADMIN_ID,
        f"⚠️ *ALERTA DE LITIGIO CON CLIENTE* :\n\n"
        f"El cliente {pseudo} (ID: {user_id}) hizo clic en *'Problema con la compra'*.\n"
        f"Recuerda comprobar que todo está bien.",
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
        await bot.send_message(chat_id=ADMIN_ID, text="❗ Utiliza el comando en respuesta a un mensaje del cliente..")
        return

    user_id = None
    if message.reply_to_message.forward_from:
        user_id = message.reply_to_message.forward_from.id
    else:
        user_id = pending_replies.get((message.chat.id, message.reply_to_message.message_id))

    if not user_id:
        await bot.send_message(chat_id=ADMIN_ID, text="❗ No se puede identificar al destinatario.")
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
        await bot.send_message(chat_id=ADMIN_ID, text="❗ Este importe no se reconoce en los enlaces disponibles.")
        return

    nouvelle_legende = re.sub(r"/env(\d+|vip)", f"{lien}", texte)

    if not (message.photo or message.video or message.document):
        await bot.send_photo(chat_id=user_id, photo=DEFAULT_FLOU_IMAGE_FILE_ID, caption=nouvelle_legende)
        await bot.send_message(
    chat_id=user_id,
    text=f"_🔒 Este contenido a {code} € está bloqueado. Haz clic en el enlace de arriba para desbloquearlo.._",
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
        await bot.send_message(chat_id=ADMIN_ID, text="❗ Utilice este comando en respuesta a un mensaje del cliente.")
        return

    user_id = None
    if message.reply_to_message.forward_from:
        user_id = message.reply_to_message.forward_from.id
    else:
        user_id = pending_replies.get((message.chat.id, message.reply_to_message.message_id))

    if not user_id:
        await bot.send_message(chat_id=ADMIN_ID, text="❗ No se puede identificar al destinatario.")
        return

    if not (message.photo or message.video or message.document):
        await bot.send_message(chat_id=ADMIN_ID, text="❗ No se detectaron medios.")
        return

    contenus_en_attente[user_id] = {
        "file_id": message.photo[-1].file_id if message.photo else message.video.file_id if message.video else message.document.file_id,
        "type": message.content_type,
        "caption": (message.caption or message.text or "").replace("/dev", "").strip()
    }

    await bot.send_message(chat_id=ADMIN_ID, text=f"✅ Contenido listo para el usuario {user_id}.")

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
@dp.message_handler(lambda message: message.text == "📖 Pedidos" and message.from_user.id == ADMIN_ID)
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

@dp.message_handler(lambda message: message.text == "📊 Estadísticas" and message.from_user.id == ADMIN_ID)
async def show_stats_direct(message: types.Message):
    await handle_stat(message)

# test du résume du dernier message recu 
import asyncio

@dp.message_handler(lambda message: message.chat.id not in authorized_admin_ids)
async def handle_admin_message(message: types.Message):
    user_id = message.from_user.id

    def escape_html(text):
        if not text:
            return "[Mensaje vacío]"
        return (
            text.replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
        )

    new_msg = escape_html(message.text)
    old_msg = escape_html(last_messages.get(user_id, "Sin mensajes"))

    last_messages[user_id] = message.text or "[Mensaje vacío]"

    await bot.forward_message(ADMIN_ID, user_id, message.message_id)

    response = (
        "╭───── 🧠 RESUMEN RÁPIDO ─────\n"
        f"📌 Antiguo : {old_msg}\n"
        f"➡️ Nuevo : {new_msg}\n"
        "╰──────────────────────────\n"
        "<i>Este mensaje se eliminará automáticamente en menos de 10 segundos.</i>"
    )

    sent_msg = await bot.send_message(ADMIN_ID, response, parse_mode="HTML")

    await asyncio.sleep(10)
    try:
        await bot.delete_message(chat_id=ADMIN_ID, message_id=sent_msg.message_id)
    except Exception as e:
        print(f"❌ Erreur suppression message : {e}")




# fin du resume du dernier message recu 

# ======================== IMPORTS & VARIABLES ========================

# ========== IMPORTS ESSENTIELS ==========
from aiogram import types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# ========== HANDLER CLIENT : transfert vers admin ==========

from ban_storage import ban_list  # à ajouter tout en haut si pas déjà fait

@dp.message_handler(lambda message: message.from_user.id != ADMIN_ID, content_types=types.ContentType.ANY)
async def relay_from_client(message: types.Message):
    user_id = message.from_user.id

    # 🔒 Vérifier si le client est banni par un admin
    for admin_id, clients_bannis in ban_list.items():
        if user_id in clients_bannis:
            try:
                await message.delete()
            except:
                pass
            try:
                await bot.send_message(user_id, "🚫 Has sido expulsado. Ya no puedes enviar mensajes.")
            except:
                pass
            return  # ⛔ STOP : on n'envoie rien à l'admin

    # ✅ Si pas banni → transfert normal
    try:
        sent_msg = await bot.forward_message(chat_id=ADMIN_ID, from_chat_id=message.chat.id, message_id=message.message_id)
        pending_replies[(sent_msg.chat.id, sent_msg.message_id)] = message.chat.id
        print(f"✅ Message reçu de {message.chat.id} et transféré à l'admin")
    except Exception as e:
        print(f"❌ Error al transferir el mensaje del cliente : {e}")



# ========== HANDLER ADMIN : réponses privées + messages groupés ==========

@dp.message_handler(lambda message: message.from_user.id == ADMIN_ID, content_types=types.ContentType.ANY)
async def handle_admin_message(message: types.Message):
    mode = admin_modes.get(ADMIN_ID)

    # ✅ Si l'admin clique sur "Message à tous les VIPs"
    if message.text == "✉️ Mensaje para todos los VIPs":
        admin_modes[ADMIN_ID] = "mensaje_en_espera"
        await bot.send_message(chat_id=ADMIN_ID, text="✍️ Qué mensaje quieres enviar a todos los VIPs ?")
        return

    # ✅ Si l'admin est en mode groupé, on traite le contenu du message
    if mode == "mensaje_en_espera":
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
        await bot.send_message(chat_id=ADMIN_ID, text="❗No se puede identificar al destinatario.")
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
            await bot.send_message(chat_id=ADMIN_ID, text="📂 Tipo de mensaje no compatible.")
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
        await message.reply("❌ Mensaje no compatible.")
        return

    confirmation = InlineKeyboardMarkup(row_width=2)
    confirmation.add(
        InlineKeyboardButton("✅ Confirmar envío", callback_data="confirmar_envío_grupal"),
        InlineKeyboardButton("❌ Cancelar envío", callback_data="cancelar_envío_grupal")
    )

    await message.reply(f"Prévisualisation :\n\n{preview}", reply_markup=confirmation)

# ========== CALLBACKS ENVOI / ANNULATION GROUPÉ ==========

@dp.callback_query_handler(lambda call: call.data == "confirmar_envío_grupal")
async def confirmer_envoi_groupé(call: types.CallbackQuery):
    await call.answer()
    message_data = pending_mass_message.get(ADMIN_ID)
    if not message_data:
        await call.message.edit_text("❌ No hay mensajes pendientes de enviar..")
        return

    await call.message.edit_text("⏳ Envío del mensaje a todos los VIPs...")
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

    await bot.send_message(chat_id=ADMIN_ID, text=f"✅ Enviado a {envoyes} VIP(s).\n⚠️ Fracasos : {erreurs}")
    pending_mass_message.pop(ADMIN_ID, None)

@dp.callback_query_handler(lambda call: call.data == "cancelar_envío_grupal")
async def annuler_envoi_groupé(call: types.CallbackQuery):
    await call.answer("❌ Envío cancelado.")
    pending_mass_message.pop(ADMIN_ID, None)
    await call.message.edit_text("❌ Envío cancelado.")

#debut du 19 juillet 2025 mettre le tableau de vips
@dp.callback_query_handler(lambda c: c.data == "ver_mis_vips")
async def voir_mes_vips(callback_query: types.CallbackQuery):
    telegram_id = callback_query.from_user.id
    email = ADMIN_EMAILS.get(telegram_id)

    if not email:
        await bot.send_message(telegram_id, "❌ Tu correo electrónico de administrador no es válido.")
        return

    await callback_query.answer("Carga de tus VIPs...")

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
        await bot.send_message(telegram_id, "📭 No se han encontrado registros para ti.")
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
        message = "📋 Aquí están tus clientes VIP (con todos sus pagos) :\n\n"
        sorted_vips = sorted(montants_par_pseudo.items(), key=lambda x: x[1], reverse=True)

        for pseudo, total in sorted_vips:
            message += f"👤 @{pseudo} — {round(total)} €\n"

        # 🏆 Top 3
        top3 = sorted_vips[:3]
        if top3:
            message += "\n🏆 *Los 3 principales clientes :*\n"
            for i, (pseudo, total) in enumerate(top3):
                place = ["🥇", "🥈", "🥉"]
                emoji = place[i] if i < len(place) else f"#{i+1}"
                message += f"{emoji} @{pseudo} — {round(total)} €\n"

        await bot.send_message(telegram_id, message)

    except Exception as e:
        import traceback
        error_text = traceback.format_exc()
        print("❌ ERREUR DANS VIPS + TOP 3 :\n", error_text)
        await bot.send_message(telegram_id, "❌ Se ha producido un error al mostrar los VIPs.")

#fin du 19 juillet 2025 mettre le tableau de vips








