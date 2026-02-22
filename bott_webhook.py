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
from middlewares.payment_filter import PaymentFilterMiddleware
from vip_topics import is_vip, get_user_id_by_topic_id, get_panel_message_id_by_user, update_vip_info, _user_topics
import re
from urllib.parse import quote
from datetime import datetime, timezone
from payment_links import create_dynamic_checkout
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from decimal import Decimal, ROUND_HALF_UP
from vip_topics import _user_topics, save_pwa_note_to_airtable
from payment_links import create_dynamic_checkout, save_payment_link_to_airtable







BOT_USERNAME = os.getenv("BOT_USERNAME")
BRIDGE_API_URL = os.getenv("BRIDGE_API_URL")  # https://novapulse-bridge.onrender.com


dp.middleware.setup(PaymentFilterMiddleware(authorized_users))


# map (chat_id, message_id) -> chat_id du client
pending_replies = {}

pending_pwa_notes = {}  # admin_id -> topic_id
pending_notes = {}  # admin_id -> user_id

# Dictionnaire temporaire pour stocker les derniers messages de chaque client
last_messages = {}
# ADMIN / OWNER / ADMINS
ADMIN_ID = 7334072965  # propriétaire historique (conserve pour compatibilité)
OWNER_ID = ADMIN_ID
# ensemble des admins autorisés (modifie/add si besoin)
authorized_admin_ids = {7334072965, 6545079601}

def is_admin(user_id: int) -> bool:
    return user_id in authorized_admin_ids or user_id == OWNER_ID


# Constantes pour le bouton VIP et la vidéo de bienvenue (défaut)
VIP_URL = "https://buy.stripe.com/7sYfZg2OxenB389gm97AI0G"
WELCOME_VIDEO_FILE_ID = "BAACAgQAAxkBAAKpUWmAlbi3I44n7CiO8xrsKNReEYgKAAJBIAACZWgAAVB4wLe2WMU9rTgE"



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
SELLER_EMAIL = os.getenv("SELLER_EMAIL")
AIRTABLE_TABLE_PROGRAMMATIONS = os.getenv("AIRTABLE_TABLE_PROGRAMMATIONS", "Programmations VIP")



# ADMIN ID
ADMIN_ID = 7334072965 # 22
DIRECTEUR_ID = 7334072965  # ID personnel au ceo pour avertir des fraudeurs

# === MEDIA EN ATTENTE ===
contenus_en_attente = {}  # { user_id: {"file_id": ..., "type": ..., "caption": ...} }
paiements_en_attente_par_user = set()  # Set de user_id qui ont payé
# === FIN MEDIA EN ATTENTE ===



def extraire_commande_env(text: str):
    match = re.search(r"/env(\d+)", text or "")
    return int(match.group(1)) if match else None

def nettoyer_commande_env(text: str):
    # supprime "/envXX" du message
    cleaned = re.sub(r"/env\d+", "", text or "").strip()
    return cleaned

#100

def create_programmation_vip_record(jour, heure_locale, run_at_utc, message_data, admin_id):
    """
    Crée une ligne dans la table 'Programmations VIP'.
    run_at_utc : datetime (UTC)
    message_data : dict venant de pending_mass_message[admin_id]
    """

    if AIRTABLE_API_KEY is None or BASE_ID is None:
        raise RuntimeError("AIRTABLE_API_KEY ou BASE_ID non configuré")

    # URL vers la table "Programmations VIP"
    url = f"https://api.airtable.com/v0/{BASE_ID}/{AIRTABLE_TABLE_PROGRAMMATIONS.replace(' ', '%20')}"

    # Conversion en ISO 8601 pour Airtable
    run_at_utc_iso = run_at_utc.isoformat().replace("+00:00", "Z")

    fields = {
        "Nom": f"{jour} {heure_locale}",
        "Jour": jour,
        "Heure locale": heure_locale,
        "RunAtUTC": run_at_utc_iso,
        "Type": message_data["type"],
        "Content": message_data["content"],
        "Caption": message_data.get("caption", ""),
        "Status": "pending",
        # "AdminID": str(admin_id),  # à activer si tu crées la colonne dans Airtable
    }

    payload = {"fields": fields}

    headers = {
        "Authorization": f"Bearer {AIRTABLE_API_KEY}",
        "Content-Type": "application/json",
    }

    resp = requests.post(url, headers=headers, json=payload)
    data = resp.json()

    if resp.status_code >= 300:
        raise RuntimeError(f"Airtable error {resp.status_code}: {data}")

    return data.get("id")

#100

# === 221097 DEBUT

def initialize_authorized_users():
    try:
        url = f"https://api.airtable.com/v0/{BASE_ID}/{TABLE_NAME.replace(' ', '%20')}"
        params = {
    "filterByFormula": "OR({Type acces}='VIP',{Type acces}='Paiement')"
}
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
# === APPELS AU DÉMARRAGE ===

initialize_authorized_users()


# 100 Pour la programmation d'envoi
pending_programmation = {}  # admin_id -> {"jour": "Lundi"}

JOUR_TO_WEEKDAY = {
    "Lundi": 0,
    "Mardi": 1,
    "Mercredi": 2,
    "Jeudi": 3,
    "Vendredi": 4,
    "Samedi": 5,
    "Dimanche": 6,
}

HEURE_REGEX = re.compile(r"^([01]?\d|2[0-3]):([0-5]\d)$")
def compute_next_run_utc(jour: str, heure_str: str) -> datetime:
    """
    jour : 'Lundi' ... 'Dimanche'
    heure_str : 'HH:MM' au format 24h
    Retourne un datetime UTC approx (on considère que l'heure donnée est en UTC pour l'instant).
    """
    now_utc = datetime.utcnow()

    match = HEURE_REGEX.match(heure_str.strip())
    if not match:
        raise ValueError(f"Heure invalide: {heure_str}")

    hour = int(match.group(1))
    minute = int(match.group(2))

    target_weekday = JOUR_TO_WEEKDAY[jour]

    # nombre de jours jusqu'au prochain 'jour'
    days_ahead = (target_weekday - now_utc.weekday()) % 7

    candidate = now_utc.replace(
        hour=hour,
        minute=minute,
        second=0,
        microsecond=0,
    )

    # si c'est aujourd'hui mais heure déjà passée → semaine prochaine
    if days_ahead == 0 and candidate <= now_utc:
        days_ahead = 7

    if days_ahead != 0:
        candidate = candidate + timedelta(days=days_ahead)

    return candidate  # datetime en UTC

# 100 FIN





# === Statistiques ===

@dp.message_handler(commands=["stat"])
async def handle_stat(message: types.Message):

    admin_id = message.from_user.id
    email = ADMIN_EMAILS.get(admin_id)

    # 🔒 Sécurité
    if not email:
        await bot.send_message(
            message.chat.id,
            "❌ Ton e-mail admin n’est pas configuré dans le bot."
        )
        return

    await bot.send_message(message.chat.id, "📥 Traitement de tes statistiques de vente en cours...")

    try:
        url = f"https://api.airtable.com/v0/{BASE_ID}/{TABLE_NAME.replace(' ', '%20')}"
        headers = {"Authorization": f"Bearer {AIRTABLE_API_KEY}"}
        params = {"filterByFormula": f"{{Email}} = '{email}'"}

        response = requests.get(url, headers=headers, params=params)
        data = response.json()

    
        ventes_totales = Decimal("0.00")
        ventes_jour = Decimal("0.00")
        nb_transactions_total = 0
        contenus_vendus_jour = 0
        vip_ids = set()

        today = datetime.now().date().isoformat()
        mois_courant = datetime.now().strftime("%Y-%m")

        # =========================
        # PARSING AIRTABLE
        # =========================
        for record in data.get("records", []):
            fields = record.get("fields", {})

            user_id = fields.get("ID Telegram", "")
            type_acces = (fields.get("Type acces", "") or "").lower()
            date_str = fields.get("Date", "") or ""
            mois = fields.get("Mois", "") or ""



            try:
                montant = Decimal(str(fields.get("Montant", 0) or 0)).quantize(
                    Decimal("0.01"), rounding=ROUND_HALF_UP
                )
            except:
                montant = Decimal("0.00")

            # ===== ventes du mois =====
            if mois == mois_courant and montant > 0 and type_acces != "vip":
                ventes_totales += montant
                nb_transactions_total += 1

            # ===== ventes du jour =====
            if date_str.startswith(today) and montant > 0 and type_acces != "vip":
                ventes_jour += montant
                contenus_vendus_jour += 1

            # ===== VIPs =====
            if user_id and montant > 0 and type_acces in ("paiement", "vip"):
                vip_ids.add(user_id)

        # =========================
        # CALCUL STRIPE PROPRE
        # =========================
        FRAIS_STRIPE_PERCENT = Decimal("0.029")
        FRAIS_STRIPE_FIXE = Decimal("0.25")
        
        frais_stripe = (
    ventes_totales * FRAIS_STRIPE_PERCENT +
    Decimal(nb_transactions_total) * FRAIS_STRIPE_FIXE
).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


        benefice_net = (ventes_totales - frais_stripe).quantize(
    Decimal("0.01"), rounding=ROUND_HALF_UP
)


        clients_vip = len(vip_ids)

        # =========================
        # MESSAGE FINAL
        # =========================
        message_final = (
            f"📊 Tes statistiques de vente :\n\n"
            f"💰 Ventes du jour : {ventes_jour:.2f}€\n"
            f"💶 Ventes totales (mois) : {ventes_totales:.2f}€\n"
            f"📦 Paiements du mois : {nb_transactions_total}\n"
            f"🌟 Clients VIP : {clients_vip}\n\n"
            f"🏦 Frais bancaires Stripe estimés : {frais_stripe:.2f}€\n"
            f"📈 Revenu net reçu : {benefice_net:.2f}€"
        )

        vip_button = InlineKeyboardMarkup().add(
            InlineKeyboardButton("📋 Voir mes VIPs", callback_data="voir_mes_vips")
        )

        await bot.send_message(
            message.chat.id,
            message_final,
            parse_mode="Markdown",
            reply_markup=vip_button
        )

    except Exception as e:
        print(f"Erreur dans /stat : {e}")
        await bot.send_message(
            message.chat.id,
            "❌ Une erreur est survenue lors de la récupération des statistiques."
        )




import requests
from datetime import datetime

def get_vip_ids_for_admin_email(email: str):
    """
    Récupère les IDs Telegram des VIPs pour un admin donné,
    en utilisant la même logique que /stat.
    """
    url = f"https://api.airtable.com/v0/{BASE_ID}/{TABLE_NAME.replace(' ', '%20')}"
    headers = {
        "Authorization": f"Bearer {AIRTABLE_API_KEY}"
    }
    params = {
        "filterByFormula": f"{{Email}} = '{email}'"
    }

    response = requests.get(url, headers=headers, params=params)
    data = response.json()

    vip_ids = set()

    for record in data.get("records", []):
        fields = record.get("fields", {})

        user_id = fields.get("ID Telegram", "")
        type_acces = (fields.get("Type acces", "") or "").lower()

        try:
            montant = Decimal(str(fields.get("Montant", 0) or 0)).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
        except:
            montant = Decimal("0.00")
        

        # 🌟 VIP = client qui a payé au moins une fois (paiement ou vip) avec montant > 0
        if user_id and montant > 0 and type_acces in ("paiement", "vip"):
            vip_ids.add(user_id)

    return vip_ids


# Liste des prix autorisés
prix_list = [1, 3, 9, 14, 19, 24, 29, 34, 39, 44, 49, 59, 69, 79, 89, 99]

# Liste blanche des liens autorisés
WHITELIST_LINKS = [
    "https://novapulseonline.wixsite.com/",
    "https://buy.stripe.com/",
    "https://t.me/NovaPulsetestbot?start=cdan"
    "https://calendar.google.com/calendar/u/0/r" # 22 Rajouter à la ligne en bas le lien propre de l'admin
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

def log_to_airtable(
    pseudo,
    user_id,
    type_acces,
    montant,
    contenu="Paiement Telegram",
    email="vinteo.ac@gmail.com",
):
    if not type_acces:
        type_acces = "Paiement"  # Par défaut pour éviter erreurs

    url_base = f"https://api.airtable.com/v0/{BASE_ID}/{TABLE_NAME.replace(' ', '%20')}"
    headers = {
        "Authorization": f"Bearer {AIRTABLE_API_KEY}",
        "Content-Type": "application/json"
    }

    now = datetime.now()

    # Champs communs qu'on veut toujours écrire / mettre à jour
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

    try:
        # 🔹 Cas particulier : accès VIP
        if str(type_acces).lower() == "vip":
            # On cherche la/les lignes VIP existantes pour ce user
            params = {
                "filterByFormula": f"AND({{ID Telegram}} = '{user_id}', {{Type acces}} = 'VIP')"
            }
            r = requests.get(url_base, headers=headers, params=params)
            r.raise_for_status()
            records = r.json().get("records", [])

            if records:
                # On choisit de préférence une ligne qui a déjà un Topic ID
                rec_to_update = records[0]
                for rec in records:
                    if rec.get("fields", {}).get("Topic ID"):
                        rec_to_update = rec
                        break

                rec_id = rec_to_update["id"]
                patch_url = f"{url_base}/{rec_id}"

                # ⚠️ Important : on n'envoie PAS "Topic ID" ici → Airtable le conserve tel quel
                data = {"fields": fields}
                response = requests.patch(patch_url, json=data, headers=headers)
            else:
                # Sécurité : si aucune ligne VIP n'existe (cas improbable),
                # on crée une nouvelle ligne comme avant
                data = {"fields": fields}
                response = requests.post(url_base, json=data, headers=headers)

        # 🔹 Tous les autres types d'accès (Paiement simple, groupé, etc.)
        else:
            data = {"fields": fields}
            response = requests.post(url_base, json=data, headers=headers)

        if response.status_code != 200:
            print(f"❌ Erreur Airtable : {response.text}")
        else:
            print("✅ Paiement ajouté dans Airtable avec succès !")

    except Exception as e:
        print(f"Erreur lors de l'envoi à Airtable : {e}")



# Création du clavier

keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
keyboard.add(
)
keyboard_admin = types.ReplyKeyboardMarkup(resize_keyboard=True)
keyboard_admin.add(
    types.KeyboardButton("📖 Commandes"),
    types.KeyboardButton("📊 Statistiques")
)

keyboard_admin.add(
    types.KeyboardButton("✉️ Message à tous les VIPs")
)

from aiogram import types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from datetime import datetime, timedelta

@dp.message_handler(commands=["start"])
async def handle_start(message: types.Message):
    user_id = message.from_user.id
    param = (message.get_args() or "").strip()
    print(f"[DEBUG START PARAM] reçu: '{param}'")

    # ============================================================
    # 🔔 NOTIFICATIONS POST-PAIEMENT (CORRIGÉES)
    # ============================================================

    # 1️⃣ Confirmation client → PWA via bridge (admin_message)
    try:
        BRIDGE_API_URL = os.getenv("BRIDGE_API_URL")
        if client_key and seller_slug and BRIDGE_API_URL:
            resp = requests.post(
                f"{BRIDGE_API_URL}/pwa/send-admin-message",
                json={
                    "email": client_key,
                    "sellerSlug": seller_slug,
                    "text": (
                        f"✅ Merci pour votre paiement de {montant_euros} € ! "
                        f"Votre facture vous sera transmise directement par mail.\n\n"
                        f"❗️Si vous avez le moindre souci avec votre commande, contactez-nous directement ici"
                    ),
                },
                timeout=5,
            )
            print(f"📩 Confirmation client PWA: {resp.status_code} {resp.text}")
    except Exception as e:
        print(f"❌ Erreur confirmation client PWA: {e}")


    # 2️⃣ Notification admins → Telegram
    try:
        from bot_webhook import authorized_admin_ids  # ajuste le nom du fichier si besoin

        for adm in authorized_admin_ids:
            try:
                await bot.send_message(
                    adm,
                    f"💰 Nouveau paiement de {montant_euros} € de {client_username}."
                )
            except Exception as e:
                print(f"[ADMIN_NOTIFY_ERROR] {e}")
    except Exception as e:
        print(f"❌ Erreur import authorized_admin_ids: {e}")


    # 3️⃣ Notification structurée → Topic staff
    try:
        from vip_topics import ensure_topic_for_vip
        topic_id = await ensure_topic_for_vip(client_username)
    except Exception:
        topic_id = None

    if topic_id is not None:
        try:
            await bot.request(
                "sendMessage",
                {
                    "chat_id": int(os.getenv("STAFF_GROUP_ID", "0")),
                    "message_thread_id": topic_id,
                    "text": (
                        f"💰 *Nouveau paiement*\n\n"
                        f"👤 Client : {client_username}\n"
                        f"💶 Montant : {montant_euros} €\n"
                        f"📊 Paiement enregistré dans ton Dashboard.\n"
                        f"📅 Planifier le RDV : https://calendar.google.com/calendar/u/0/r"
                    ),
                    "parse_mode": "Markdown"
                }
            )
        except Exception as e:
            print(f"[VIP_TOPICS_ERROR] {e}")


    # === Cas B : /start=vipcdan (retour après paiement VIP) ===
    if param == "vipcdan":
        # 1) Le user devient VIP côté système (payeurs)
        authorized_users.add(user_id)

        # 2) On crée / récupère le topic pour ce client
        try:
            from vip_topics import ensure_topic_for_vip
            topic_id = await ensure_topic_for_vip(message.from_user)
        except Exception as e:
            print(f"[VIP] Erreur ensure_topic_for_vip pour {user_id}: {e}")
            topic_id = None  # pour éviter un NameError plus loin

        # 3) Log Airtable en tant que VIP (sans envoyer de cadeau auto au client)
        log_to_airtable(
            pseudo=message.from_user.username or message.from_user.first_name,
            user_id=user_id,
            type_acces="VIP",
            montant=9.0,  # adapte si besoin selon ton lien Stripe VIP
            contenu="Accès VIP confirmé via Stripe"
        )

        # 4) Notifier tous les admins (mais pas le client)
        for adm in authorized_admin_ids:
            try:
                await bot.send_message(
                    adm,
                    f"🌟 Nouveau VIP confirmé : {message.from_user.username or message.from_user.first_name} (paiement VIP)."
                )
            except Exception:
                pass

        # 5) Notification dans le TOPIC du client (si on a réussi à le récupérer)
        if topic_id is not None:
            try:
                await bot.request(
                    "sendMessage",
                    {
                        "chat_id": int(os.getenv("STAFF_GROUP_ID", "0")),
                        "message_thread_id": topic_id,
                        "text": (
                            f"🌟 *Nouveau VIP confirmé*\n\n"
                            f"👤 Client : @{message.from_user.username or message.from_user.first_name}\n"
                            f"💶 Montant : 9 €\n"
                            f"📊 Accès VIP enregistré dans le dashboard."
                        ),
                        "parse_mode": "Markdown"
                    }
                )
            except Exception as e:
                print(f"[VIP_TOPICS] Erreur envoi notif VIP dans topic {topic_id} : {e}")

        # ⚠️ Important : on NE renvoie RIEN au client ici.
        # Il continue à parler normalement, il recevra seulement les contenus que l'admin lui vend.
        return  # on sort ici pour ne pas passer à l’accueil normal

    # === Cas C : /start simple (accueil normal) ===
    if is_admin(user_id):
        await bot.send_message(
            user_id,
            "👋 Bonjour admin ! Tu peux voir le listing des commandes et consulter tes statistiques !",
            reply_markup=keyboard_admin
        )
        return

    # 1) Texte d’accueil pour un client qui arrive pour la première fois
    await bot.send_message(
        user_id,
        "Bienvenue chez NovaPulse !"
    )

    # 2️⃣ Bouton inline "Voir mes services"
    inline_kb = InlineKeyboardMarkup()
    inline_kb.add(
        InlineKeyboardButton("📋 Voir mes services", callback_data="voir_services")
    )

    # 3️⃣ Vidéo + bouton
    # 3️⃣ Vidéo + bouton
    with open("assets/intro.mp4", "rb") as video_file:
        await bot.send_video(
        chat_id=user_id,
        video=video_file,
        caption="Découvrez nos prestations ci-dessous 👇",
        reply_markup=inline_kb
    )


# =========================
# BOUTON SERVICES
# =========================
@dp.callback_query_handler(lambda c: c.data == "voir_services")
async def handle_services(call: types.CallbackQuery):

    texte = (
        "📋 *Nos services disponibles :*\n\n"
        "• Traduction simple — 29€\n"
        "• Lavage complet véhicule — 49€\n"
        "• Dossier financement — 99€\n"
        "• Consultation — 65€\n\n"
        "Envoyez-nous un message pour réserver ou pour plus d'informations 😊"
    )

    await bot.send_message(
        call.message.chat.id,
        texte,
        parse_mode="Markdown"
    )

    await call.answer()


    # Envoi à tous les admins (vendeurs)
    try:
        for adm in authorized_admin_ids:
            await bot.send_message(adm, texte_alerte_admin, parse_mode="Markdown")
    except Exception as e:
        print(f"Erreur envoi admin : {e}")

    # Envoi au directeur (toi)
    try:
        await bot.send_message(DIRECTEUR_ID, texte_alerte_directeur, parse_mode="Markdown")
    except Exception as e:
        print(f"Erreur envoi directeur : {e}")


# TEST  DEBUT

@dp.message_handler(
    lambda m: m.chat.id == STAFF_GROUP_ID and m.from_user.id in pending_notes,
    content_types=[types.ContentType.TEXT]
)
async def handle_vip_note(message: types.Message):
    admin_id = message.from_user.id

    # DEBUG
    print(f"[NOTES] handle_vip_note triggered for admin_id={admin_id}, chat_id={message.chat.id}")
    print(f"[NOTES] pending_notes = {pending_notes}")

    # Récupérer le VIP concerné et enlever le mode "note"
    vip_user_id = pending_notes.pop(admin_id, None)
    if not vip_user_id:
        return

    # 🔥 NOUVEAU : récupération du topic_id
    entry = _user_topics.get(vip_user_id, {})
    topic_id = entry.get("topic_id")

    if not topic_id:
        await message.reply("⚠️ Impossible de trouver le topic pour cette conversation.")
        raise CancelHandler()

    note_text = (message.text or "").strip()
    if not note_text:
        await message.reply("❌ Note vide, rien n'a été enregistré.")
        raise CancelHandler()

    print(f"[NOTES] Note reçue pour VIP user_id={vip_user_id} par admin_id={admin_id} : {note_text}")

    # 🔥 Enregistrement dans Airtable PWA Notes
    seller_slug = "coach-matthieu"  # adapter si multi-sellers plus tard
    save_pwa_note_to_airtable(topic_id, seller_slug, note_text)

    # Mise à jour des infos VIP (NOTE CONCATÉNÉE pour le panel Telegram)
    info = update_vip_info(vip_user_id, note=note_text)

    # 🔥 On récupère un panel valide (recréé si nécessaire)
    panel_message_id = await get_panel_message_id_by_user(vip_user_id)

    admin_name = info.get("admin_name") or "Aucun"
    full_note = info.get("note", note_text)

    if not panel_message_id:
        await message.reply("⚠️ Impossible de retrouver ou recréer le panneau VIP pour ce client.")
        raise CancelHandler()

    panel_text = (
        "🧐 PANEL DE CONTRÔLE VIP\n\n"
        f"👤 Client : {vip_user_id}\n"
        f"📒 Notes : {full_note}\n"
        f"👤 Admin en charge : {admin_name}"
    )

    kb = InlineKeyboardMarkup()
    kb.add(
        InlineKeyboardButton("✅ Prendre en charge", callback_data=f"prendre_{vip_user_id}"),
        InlineKeyboardButton("📝 Ajouter une note", callback_data=f"annoter_{vip_user_id}")
    )

    # Mise à jour du panneau existant (aucune duplication)
    await bot.edit_message_text(
        chat_id=STAFF_GROUP_ID,
        message_id=panel_message_id,
        text=panel_text,
        reply_markup=kb
    )

    # Confirmation dans le topic
    await message.reply("✅ Note enregistrée et panneau mis à jour.", reply=False)

    # Empêche les autres handlers de traiter ce message
    raise CancelHandler()


# TEST A SUPPRIMER FIN


# Message et média personnel avec lien

    # ================================
# PWA RESOLVER (via topic_id Airtable)
# ================================
import os
import re
import requests
from decimal import Decimal, ROUND_HALF_UP
from aiogram import types

def get_pwa_client_by_topic(thread_id: int):
    try:
        airtable_api_key = os.getenv("AIRTABLE_API_KEY")
        base_id = os.getenv("AIRTABLE_BASE_ID") or os.getenv("BASE_ID")

        if not airtable_api_key or not base_id or not thread_id:
            print("[PWA LOOKUP] Missing env or thread_id")
            return None

        url = f"https://api.airtable.com/v0/{base_id}/PWA%20Clients"
        headers = {"Authorization": f"Bearer {airtable_api_key}"}
        params = {"filterByFormula": f"{{topic_id}}='{thread_id}'"
}


        resp = requests.get(url, headers=headers, params=params, timeout=8)
        records = resp.json().get("records", [])

        if not records:
            print(f"[PWA LOOKUP] No Airtable record for topic {thread_id}")
            return None

        fields = records[0]["fields"]
        email = fields.get("email")
        seller_slug = fields.get("seller_slug") or fields.get("sellerSlug")

        if not email or not seller_slug:
            print("[PWA LOOKUP] Missing email or seller_slug")
            return None

        return {
            "email": email.strip().lower(),
            "seller_slug": seller_slug.strip().lower()
        }

    except Exception as e:
        print(f"[PWA LOOKUP ERROR] {e}")
        return None


# ================================
# UTILS
# ================================
def parse_amount_to_cents(amount_str: str) -> int:
    normalized = amount_str.replace(",", ".").strip()
    amount = Decimal(normalized).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return int(amount * 100)
def nettoyer_commande_env(texte: str) -> str:
    """
    Supprime la commande /envXX du texte pour ne garder
    que le message destiné au client.
    """
    if not texte:
        return ""
    return re.sub(r"/env([\d.,]+|vip)", "", texte, flags=re.IGNORECASE).strip()


from aiogram.dispatcher.handler import CancelHandler

# ================================
# HANDLER /envXX → PWA + MEDIA UPLOAD
# ================================
@dp.message_handler(
    lambda m: (m.text or m.caption) and "/env" in (m.text or m.caption).lower(),
    content_types=types.ContentType.ANY
)
async def envoyer_contenu_payant(message: types.Message):
    admin_id = message.from_user.id

    # 🔒 Sécurité : seul un admin peut utiliser /env
    if not is_admin(admin_id):
        raise CancelHandler()

    # 🔒 Empêche TOUT autre handler (notamment handle_admin_message)
    # de traiter ce message et d'envoyer le texte brut au client
    # (cause principale des doublons + fuite du /envXX)
    try:
        texte = message.caption or message.text or ""

        # On vérifie qu'il y a bien un code /envXX valide
        if not re.search(r"/env[\d.,]+", texte.lower()):
            await bot.send_message(
                chat_id=admin_id,
                text="❗ Commande /env invalide. Exemple : /env49"
            )
            raise CancelHandler()

        # 👉 À partir d’ici, TON CODE EXISTANT CONTINUE
        # (parse montant, upload media, envoi PWA, etc.)

    except Exception as e:
        print(f"[ENV HANDLER ERROR] {e}")
        raise CancelHandler()


    # ================================
    # DEBUG TELEGRAM RAW
    # ================================
    print("RAW MESSAGE:", message.to_python())

    # ================================
    # DETECTION DU TOPIC
    # ================================
    thread_id = None
    raw = message.to_python()
    thread_id = raw.get("message_thread_id")

    if not thread_id and message.reply_to_message:
        raw_reply = message.reply_to_message.to_python()
        thread_id = raw_reply.get("message_thread_id")

    print(f"[TOPIC DETECTED] {thread_id}")

    # ================================
    # RESOLVE CLIENT PWA
    # ================================
    client = get_pwa_client_by_topic(thread_id)
    print(f"[PWA RESOLVE] topic={thread_id} -> client={client}")

    if not client:
        await bot.send_message(
            chat_id=admin_id,
            text="❗ Aucun client PWA trouvé pour ce topic."
        )
        return

    email = client["email"]
    seller_slug = client["seller_slug"]

        # ================================
    # PARSE /envXX + NETTOYAGE TEXTE
    # ================================
    texte = message.caption or message.text or ""
    match = re.search(r"/env([\d.,]+|vip)", texte.lower())

    if not match:
        await bot.send_message(chat_id=admin_id, text="❗ Code /env invalide.")
        return

    raw_code = str(match.group(1)).lower()

    # 🔥 IMPORTANT : on nettoie le texte pour la PWA
    nouvelle_legende = nettoyer_commande_env(texte)

    if raw_code == "vip":
        await bot.send_message(chat_id=admin_id, text="❗ /envvip n'est pas géré ici. Utilise un montant (ex: /env9).")
        return

    amount_cents = parse_amount_to_cents(raw_code)
    display_amount = format(amount_cents / 100, ".2f").replace(".", ",")

    # ✅ Identifiants robustes pour l’après-paiement
    client_key = email  # PWA client key = email (stable)
    content_id = f"{seller_slug}_{int(datetime.utcnow().timestamp())}"

    # ✅ Stripe checkout avec metadata + session_id
    checkout_url, session_id = create_dynamic_checkout(
        amount_cents=amount_cents,
        client_key=client_key,
        content_id=content_id,
        seller_slug=seller_slug,
        admin_id=str(admin_id),
    )

    # ✅ Airtable: on log la ligne Pending avec session_id (indispensable)
    save_payment_link_to_airtable(
        client_key=client_key,
        content_id=content_id,
        payment_link=checkout_url,
        admin_id=str(admin_id),
        amount_cents=amount_cents,
        checkout_session_id=session_id,
    )
    # ================================
    # PARSE /envXX
    # ================================
    texte = message.caption or message.text or ""
    match = re.search(r"/env([\d.,]+|vip)", texte.lower())

    if not match:
        await bot.send_message(chat_id=admin_id, text="❗ Code /env invalide.")
        return

    raw_code = str(match.group(1)).lower()

    # 🔥 ICI EXACTEMENT (juste après le match)
    nouvelle_legende = nettoyer_commande_env(texte)

    if raw_code == "vip":
        await bot.send_message(chat_id=admin_id, text="❗ /envvip n'est pas géré ici. Utilise un montant (ex: /env9).")
        return

    # ================================
    # NOUVEAU : UPLOAD MEDIA VERS BRIDGE
    # ================================
    media_url = None
    is_media = bool(message.photo or message.video or message.document)

    if is_media:
        try:
            if message.photo:
                file_id = message.photo[-1].file_id
            elif message.video:
                file_id = message.video.file_id
            else:
                file_id = message.document.file_id

            tg_file = await bot.get_file(file_id)
            file_bytes = await bot.download_file(tg_file.file_path)

            files = {
                "file": ("media_file", file_bytes.read())
            }
            data = {
                "sellerSlug": seller_slug,
                "clientEmail": email,
                "amount": amount_cents
            }

            print("[BRIDGE UPLOAD] sending media...")
            resp = requests.post(
                f"{BRIDGE_API_URL}/upload-media",
                files=files,
                data=data,
                timeout=20
            )

            result = resp.json()
            print("[BRIDGE RESPONSE]", result)

            if result.get("success"):
                media_url = result.get("mediaUrl")
            else:
                await bot.send_message(
                    chat_id=admin_id,
                    text="❌ Erreur upload média vers le bridge."
                )
                return

        except Exception as e:
            print(f"[UPLOAD ERROR] {e}")
            await bot.send_message(
                chat_id=admin_id,
                text="❌ Échec upload média (bridge)."
            )
            return

    # ================================
    # ROUTEUR FINAL → PWA
    # ================================
    try:
        payload = {
            "email": email,
            "sellerSlug": seller_slug,
            "text": nouvelle_legende or "💳 Paiement requis.",
            "checkout_url": checkout_url,
            "contentId": content_id,
            "sessionId": session_id,
            "isMedia": is_media,
            "mediaUrl": media_url,  # 🔥 IMPORTANT
            "amount": amount_cents,
        }

        if is_media:
            # 🔥 Flow paywall classique (inchangé)
            requests.post(
                f"{BRIDGE_API_URL}/pwa/send-paid-content",
                json=payload,
                timeout=5,
            )
        else:
            # 💳 Paiement simple sans média
            simple_payload = {
                "email": email,
                "sellerSlug": seller_slug,
                "text": "💳 Paiement requis.",
                "checkout_url": checkout_url,
                "amount": amount_cents,
            }

            requests.post(
                f"{BRIDGE_API_URL}/pwa/send-simple-payment",
                json=simple_payload,
                timeout=5,
            )

        print(f"[PWA SEND OK] {email}")

    except Exception as e:
        print(f"[PWA ERROR] {e}")

    await bot.send_message(
        chat_id=admin_id,
        text=f"✅ Paiement {display_amount}€ envoyé au client PWA.",
    )

    # ================================
    # CAS SPECIAL : notes VIP (inchangé)
    # ================================
    if admin_id in pending_notes:
        vip_user_id = pending_notes.pop(admin_id)
        note_text = (message.text or message.caption or "").strip()

        if not note_text:
            await bot.send_message(chat_id=admin_id, text="❗ Note vide.")
            return

        info = update_vip_info(vip_user_id, note=note_text)
        topic_id = info.get("topic_id")
        panel_message_id = await get_panel_message_id_by_user(vip_user_id)

        admin_name = (
            info.get("admin_name")
            or message.from_user.username
            or message.from_user.first_name
            or str(admin_id)
        )

        full_note = info.get("note", note_text)

        if topic_id and panel_message_id:
            panel_text = (
                "🧐 PANEL DE CONTRÔLE VIP\n\n"
                f"👤 Client : {vip_user_id}\n"
                f"📒 Notes : {full_note}\n"
                f"👤 Admin en charge : {admin_name}"
            )

            kb = InlineKeyboardMarkup()
            kb.add(
                InlineKeyboardButton("✅ Prendre en charge", callback_data=f"prendre_{vip_user_id}"),
                InlineKeyboardButton("📝 Ajouter une note", callback_data=f"annoter_{vip_user_id}")
            )

            await bot.edit_message_text(
                chat_id=STAFF_GROUP_ID,
                message_id=panel_message_id,
                text=panel_text,
                reply_markup=kb
            )
        else:
            await bot.send_message(
                chat_id=admin_id,
                text="⚠️ Impossible de retrouver ou recréer le panneau VIP."
            )
            return

        await bot.send_message(chat_id=admin_id, text="✅ Note enregistrée.")
        return

    return





@dp.message_handler(lambda message: message.text == "📖 Commandes" and is_admin(message.from_user.id))
async def show_commandes_admin(message: types.Message):
    commandes = (
        "📖 *Liste des commandes disponibles :*\n\n"
        "🔒 */envxx* – Envoyer un contenu payant ou juste le lien de paiment €\n"
        "_Tape cette commande avec le bon montant (ex. /env14) pour envoyer un contenu flouté avec lien de paiement de 14 €. Ton client recevra directement une image floutée avec le lien de paiement._\n\n"
        "_ou_\n\n"
        "_Tape cette commande avec le bon montant (ex. /env14) sans images, ni videos ou fichiers. Ton client recevra directement son lien de paiment._\n\n"
        "⚠️ ** – N'oublies pas de sélectionner le message du client à qui tu veux répondre\n\n"
        "⚠️ ** – Voici la liste des prix : 9, 14, 19, 24.....\n\n"
        "📬 *Besoin d’aide ?* Écris-moi par mail : novapulse.online@gmail.com"
    )

    # Création du bouton inline "Mise à jour"
    inline_keyboard = InlineKeyboardMarkup()
    inline_keyboard.add(InlineKeyboardButton("🛠️ Mise à jour", callback_data="maj_bot"))

    await message.reply(commandes, parse_mode="Markdown", reply_markup=inline_keyboard)


# Callback quand on clique sur le bouton inline
@dp.callback_query_handler(lambda call: call.data == "maj_bot")
async def handle_maj_bot(call: types.CallbackQuery):
    await bot.answer_callback_query(call.id)
    await bot.send_message(call.message.chat.id, "🔄 Clique pour lancer la MAJ ➡️ : /start")

@dp.message_handler(lambda message: message.text == "📊 Statistiques" and is_admin(message.from_user.id))
async def show_stats_direct(message: types.Message):
    await handle_stat(message)


# ======================== IMPORTS & VARIABLES ========================

# ========== HANDLER ADMIN : réponses privées + messages groupés ==========

@dp.message_handler(lambda message: is_admin(message.from_user.id), content_types=types.ContentType.ANY)
async def handle_admin_message(message: types.Message):
    admin_id = message.from_user.id
    mode = admin_modes.get(admin_id)

    print(
        f"[ADMIN_MSG] from admin_id={admin_id}, chat_id={message.chat.id}, "
        f"reply_to={getattr(message.reply_to_message, 'message_id', None)}"
    )

# 100       # 0) COMMANDE DE TEST DU SCHEDULER
    if message.text == "/test_scheduler":
        await message.reply("⏳ Test du scheduler en cours...")
        try:
            await process_due_programmations_once()
            await message.reply("✅ Scheduler exécuté une fois. Vérifie Airtable et les logs.")
        except Exception as e:
            await message.reply(f"❌ Erreur dans le scheduler : {e}")
            print(f"[SCHEDULE] Erreur via /test_scheduler : {e}")
        return
    
            # 0) MODE SAISIE HEURE POUR PROGRAMMATION
    if mode == "en_attente_heure_prog":
        if not message.text:
            await bot.send_message(
                chat_id=admin_id,
                text="❌ Merci d'envoyer uniquement l'heure au format 24h, par ex. 10:00."
            )
            return

        heure_str = message.text.strip()

        if not HEURE_REGEX.match(heure_str):
            await bot.send_message(
                chat_id=admin_id,
                text="❌ Format invalide. Exemples valides : 09:30, 14:05, 21:00."
            )
            return

        prog_ctx = pending_programmation.get(admin_id)
        message_data = pending_mass_message.get(admin_id)

        if not prog_ctx or not message_data:
            # plus de contexte → on reset
            admin_modes[admin_id] = None
            pending_programmation.pop(admin_id, None)
            await bot.send_message(
                chat_id=admin_id,
                text="❌ Plus aucun message en attente de programmation."
            )
            return

        jour = prog_ctx["jour"]

        # 🕒 1) On calcule la prochaine date d'exécution en UTC
        try:
            run_at_utc = compute_next_run_utc(jour, heure_str)
        except Exception as e:
            await bot.send_message(
                chat_id=admin_id,
                text=f"❌ Erreur lors du calcul de la date d'envoi : {e}"
            )
            return

        # 🗄️ 2) On ENREGISTRE maintenant dans Airtable
        try:
            record_id = create_programmation_vip_record(
                jour=jour,
                heure_locale=heure_str,
                run_at_utc=run_at_utc,
                message_data=message_data,
                admin_id=admin_id,
            )
        except Exception as e:
            print(f"[SCHEDULE] Erreur Airtable : {e}")
            await bot.send_message(
                chat_id=admin_id,
                text=(
                    "❌ Impossible d'enregistrer la programmation dans Airtable pour le moment.\n"
                    "Réessaie plus tard ou contacte Nova Pulse."
                )
            )
            return

        # 3) Reset des états liés à la programmation
        admin_modes[admin_id] = None
        pending_programmation.pop(admin_id, None)
        pending_mass_message.pop(admin_id, None)

        run_at_utc_str = run_at_utc.strftime("%Y-%m-%d %H:%M UTC")

        await bot.send_message(
            chat_id=admin_id,
            text=(
                "📅 *Programmation créée avec succès !*\n\n"
                f"• Jour : *{jour}*\n"
                f"• Heure locale : *{heure_str}*\n"
                f"• Exécution prévue (UTC) : *{run_at_utc_str}*\n\n"
                "✅ Elle est maintenant enregistrée avec le statut *pending*.\n"
            ),
            parse_mode="Markdown"
        )
        return


# 100
    # 1) MENU ENVOI GROUPÉ
    if message.text == "✉️ Message à tous les VIPs":
        kb = InlineKeyboardMarkup()
        kb.add(
            InlineKeyboardButton("📩 Message gratuit", callback_data="vip_message_gratuit")
        )
        await bot.send_message(
            chat_id=admin_id,
            text="🧩 Choisis le type de message à envoyer à tous les VIPs :",
            reply_markup=kb
        )
        return

    # 2) MODE DIFFUSION GROUPÉE
    if mode == "en_attente_message":
        admin_modes[admin_id] = None
        await traiter_message_groupé(message, admin_id=admin_id)
        return
            # 🔹 Ignorer les topics PWA (gérés par le Bridge)
    if message.chat.id == STAFF_GROUP_ID:
        thread_id = getattr(message, "message_thread_id", None)

        if thread_id:
            try:
                topic = await bot.get_forum_topic(
                    chat_id=STAFF_GROUP_ID,
                    message_thread_id=thread_id
                )

                topic_name = topic.name

                if topic_name.startswith("[PWA]"):
                    print(f"[ADMIN_MSG] Topic PWA ignoré : {topic_name}")
                    return

            except Exception as e:
                print(f"[ADMIN_MSG] Erreur récupération topic : {e}")




    # 🔹 Ignorer les topics PWA (gérés par le Bridge) PWA

    # 3) RÉPONSE À UN CLIENT (COMPORTEMENT NORMAL)

    # 🔐 On oblige : reply + dans le STAFF_GROUP
    if not message.reply_to_message or message.chat.id != STAFF_GROUP_ID:
        await bot.send_message(
            chat_id=admin_id,
            text="❗Pour répondre à un client, réponds en *reply* au message transféré du client dans le groupe staff (dans son topic).",
            parse_mode="Markdown"
        )
        return

    replied_msg_id = message.reply_to_message.message_id
    key = (message.chat.id, replied_msg_id)
    user_id = pending_replies.get(key)

    print(f"[ADMIN_MSG] lookup pending_replies key={key} -> user_id={user_id}")

    # 🔥 Sécurité : on refuse d'envoyer vers un admin
    if (
        not user_id
        or user_id == admin_id
        or user_id in authorized_admin_ids
        or user_id == OWNER_ID
    ):
        await bot.send_message(
            chat_id=admin_id,
            text="❗Impossible d'identifier le *client* destinataire. "
                 "Réponds bien au **dernier message transféré du client** dans son topic.",
            parse_mode="Markdown"
        )
        return

    # 4) Envoi vers le client
    try:
        if message.text:
            await bot.send_message(chat_id=user_id, text=message.text)

        elif message.photo:
            await bot.send_photo(
                chat_id=user_id,
                photo=message.photo[-1].file_id,
                caption=message.caption or ""
            )

        elif message.video:
            await bot.send_video(
                chat_id=user_id,
                video=message.video.file_id,
                caption=message.caption or ""
            )

        elif message.document:
            await bot.send_document(
                chat_id=user_id,
                document=message.document.file_id,
                caption=message.caption or ""
            )

        elif message.voice:
            await bot.send_voice(
                chat_id=user_id,
                voice=message.voice.file_id
            )

        elif message.audio:
            await bot.send_audio(
                chat_id=user_id,
                audio=message.audio.file_id,
                caption=message.caption or ""
            )

        else:
            await bot.send_message(
                chat_id=admin_id,
                text="📂 Type de message non supporté."
            )

    except Exception as e:
        await bot.send_message(
            chat_id=admin_id,
            text=f"❗Erreur admin -> client : {e}"
        )





# ========== IMPORTS ESSENTIELS ==========
from aiogram import types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# ========== HANDLER CLIENT : transfert vers admin ==========

from ban_storage import ban_list  # à ajouter tout en haut si pas déjà fait


STAFF_GROUP_ID = int(os.getenv("STAFF_GROUP_ID", "0"))

@dp.message_handler(
    lambda message: message.chat.type == "private" and not is_admin(message.from_user.id),
    content_types=types.ContentType.ANY
)
async def relay_from_client(message: types.Message):
    """
    Tous les clients (VIP ou non) sont transférés dans un topic dédié
    dans le STAFF_GROUP. Le statut VIP sert uniquement aux stats / envois groupés.
    """
    user_id = message.from_user.id
    print(f"[RELAY] message from {user_id} (chat {message.chat.id}), authorized={user_id in authorized_users}")

    # 1) Vérifier la ban_list
    for admin_id, clients_bannis in ban_list.items():
        if user_id in clients_bannis:
            try:
                await message.delete()
            except Exception:
                pass
            try:
                await bot.send_message(
                    user_id,
                    "🚫 Tu as été banni, tu ne peux plus envoyer de messages."
                )
            except Exception:
                pass
            return

    # 2) 🔎 Détection des mots "call" / "custom" (UNIQUEMENT TEXTE)
    if message.content_type == types.ContentType.TEXT:
        texte = (message.text or "").lower()
        if any(mot in texte for mot in ("call", "custom")):
            try:
                await bot.send_message(
                    DIRECTEUR_ID,
                    (
                        "📞 Mot clé détecté : *call/custom*\n\n"
                        f"👤 User : @{message.from_user.username or message.from_user.first_name}\n"
                        f"🆔 ID : `{message.from_user.id}`\n"
                        f"💬 Message : {message.text}"
                    ),
                    parse_mode="Markdown"
                )
            except Exception as e:
                print(f"Erreur lors de l'avertissement du directeur : {e}")

    # 3) Création / récupération du topic dédié pour ce client + transfert
    topic_id = None
    try:
        from vip_topics import ensure_topic_for_vip
        topic_id = await ensure_topic_for_vip(message.from_user)

        res = await bot.request(
            "forwardMessage",
            {
                "chat_id": STAFF_GROUP_ID,
                "from_chat_id": message.chat.id,
                "message_id": message.message_id,
                "message_thread_id": topic_id,
            }
        )

        sent_msg_id = res.get("message_id")
        if sent_msg_id:
            pending_replies[(STAFF_GROUP_ID, sent_msg_id)] = message.chat.id

        print(f"✅ Message client reçu de {message.chat.id} et transféré dans le topic {topic_id}")

    except Exception as e:
        print(f"❌ Erreur transfert message client vers topic : {e}")


# 1. code pour le bouton prendre en charge début

@dp.callback_query_handler(lambda c: c.data.startswith("prendre_"))
async def handle_prendre_en_charge(callback_query: types.CallbackQuery):
    admin_id = callback_query.from_user.id
    data = callback_query.data  # ex: "prendre_8440217096"

    try:
        vip_user_id = int(data.split("_", 1)[1])
    except Exception:
        await callback_query.answer("ID VIP invalide.", show_alert=True)
        return

    # Déterminer le nom de l'admin
    admin_name = (
        callback_query.from_user.username
        or callback_query.from_user.first_name
        or str(admin_id)
    )

    print(f"[VIP] Admin {admin_id} prend en charge VIP {vip_user_id} ({admin_name})")

    # On met à jour les infos VIP (ADMIN UNIQUEMENT)
    info = update_vip_info(
        vip_user_id,
        admin_id=admin_id,
        admin_name=admin_name,
    )

    panel_message_id = await get_panel_message_id_by_user(vip_user_id)
    note_text = info.get("note", "")

    if not panel_message_id:
        await callback_query.answer("Panneau introuvable pour ce VIP.", show_alert=True)
        return

    panel_text = (
        "🧐 PANEL DE CONTRÔLE VIP\n\n"
        f"👤 Client : {vip_user_id}\n"
        f"📒 Notes : {note_text}\n"
        f"👤 Admin en charge : {admin_name}"
    )

    kb = InlineKeyboardMarkup()
    kb.add(
        InlineKeyboardButton("✅ Prendre en charge", callback_data=f"prendre_{vip_user_id}"),
        InlineKeyboardButton("📝 Ajouter une note", callback_data=f"annoter_{vip_user_id}")
    )

    # On met à jour le panneau
    await bot.edit_message_text(
        chat_id=STAFF_GROUP_ID,
        message_id=panel_message_id,
        text=panel_text,
        reply_markup=kb
    )

    await callback_query.answer("✅ Tu es maintenant en charge de ce VIP.")



# 1. code pour le bouton prendre en charge fin

# 1. code pour le bouton annoter début



@dp.callback_query_handler(lambda c: c.data and c.data.startswith("annoter_"))
async def handle_annoter_vip(callback_query: types.CallbackQuery):
    admin_id = callback_query.from_user.id

    # Vérifier qu'on clique bien depuis le STAFF_GROUP
    if callback_query.message.chat.id != STAFF_GROUP_ID:
        await callback_query.answer("Action réservée au staff.", show_alert=True)
        return

    # Récupère l'user_id du VIP depuis la callback
    try:
        user_id = int(callback_query.data.split("_", 1)[1])
    except Exception:
        await callback_query.answer("Données invalides.", show_alert=True)
        return

    # Si l'admin est déjà en mode note, renvoyer une info et ne rien re-créer
    if admin_id in pending_notes:
        current_target = pending_notes.get(admin_id)
        # Si c'est pour le même client, on informe
        if current_target == user_id:
            await callback_query.answer("📝 Tu es déjà en mode annotation pour ce client. Envoie ta note dans le topic.", show_alert=False)
            return
        # Sinon, prévenir que l'admin est déjà en mode note pour un autre client
        await callback_query.answer("🔔 Tu es actuellement en mode annotation pour un autre client. Termine ou annule d'abord.", show_alert=True)
        return

    # On récupère les infos déjà stockées (topic_id, panel_message_id, etc.)
    info = update_vip_info(user_id)
    topic_id = info.get("topic_id")

    if not topic_id:
        await callback_query.answer("Impossible de retrouver le topic VIP.", show_alert=True)
        return

    # 🔥 Vérifie/crée le panel si nécessaire
    panel_id = await get_panel_message_id_by_user(user_id)



    # On passe cet admin en "mode note" pour ce user_id
    pending_notes[admin_id] = user_id

    # Marquer l'admin comme "en train d'annoter" visuellement (ferme le loader)
    await callback_query.answer()

    # ⚠️ ICI : on utilise bot.request pour poster DANS LE TOPIC
    try:
        await bot.request(
            "sendMessage",
            {
                "chat_id": STAFF_GROUP_ID,
                "message_thread_id": topic_id,
                "text": (
                    f"📝 Envoie maintenant ta note pour le client {user_id} dans ce topic.\n"
                    "➡️ Le prochain message que tu écris ici sera enregistré comme NOTE.\n\n"
                    "Si tu veux annuler : envoie `/annuler_note`."
                ),
            },
        )
    except Exception as e:
        # Nettoyage si envoi échoue (pour éviter rester bloqué en pending)
        pending_notes.pop(admin_id, None)
        print(f"[NOTES] Erreur envoi prompt annotation (callback annoter_) : {e}")
        await callback_query.answer("Impossible d'envoyer l'invite d'annotation.", show_alert=True)


@dp.callback_query_handler(lambda c: True)
async def debug_all_callbacks(callback_query: types.CallbackQuery):
    print("📌 CALLBACK REÇU :", callback_query.data)
    await callback_query.answer()

# 1. code pour le bouton annoter fin
@dp.callback_query_handler(lambda c: c.data.startswith("annoter_pwa_"))
async def handle_annoter_pwa(callback_query: types.CallbackQuery):
    admin_id = callback_query.from_user.id

    try:
        topic_id = int(callback_query.data.split("_")[-1])
    except Exception:
        await callback_query.answer("Topic invalide.", show_alert=True)
        return

    # On met l'admin en mode "attente de note" pour CE topic
    pending_pwa_notes[admin_id] = topic_id

    await callback_query.answer()
    await bot.send_message(
        chat_id=STAFF_GROUP_ID,
        message_thread_id=topic_id,
        text="📝 Envoie maintenant la note pour ce client."
    )
@dp.message_handler(
    lambda m: m.chat.id == STAFF_GROUP_ID and m.from_user.id in pending_pwa_notes,
    content_types=[types.ContentType.TEXT]
)
async def handle_pwa_note(message: types.Message):
    admin_id = message.from_user.id
    topic_id = pending_pwa_notes.pop(admin_id, None)

    if not topic_id:
        return

    note_text = (message.text or "").strip()
    if not note_text:
        await message.reply("❌ Note vide, rien n'a été enregistrée.")
        return

    print(f"[PWA NOTES] Note reçue topic_id={topic_id} admin={admin_id}: {note_text}")

    # 🔥 1) Sauvegarde dans Airtable PWA Notes (historique)
    seller_slug = "coach-matthieu"  # à rendre dynamique plus tard
    save_pwa_note_to_airtable(topic_id, seller_slug, note_text)

    # 🔥 2) Mettre à jour la note principale dans PWA Clients (champ admin_note)
    try:
        await axios_post_update_pwa_note(topic_id, seller_slug, note_text)
    except Exception as e:
        print("[PWA NOTES] Erreur update admin_note:", e)

    # 🔥 3) Mise à jour du panel Telegram
    panel_text = (
        "🧐 PANEL DE CONTRÔLE PWA\n\n"
        f"🧵 Topic : {topic_id}\n"
        f"📒 Dernière note : {note_text}\n"
        f"👤 Admin en charge : {message.from_user.first_name}"
    )

    kb = InlineKeyboardMarkup()
    kb.add(
        InlineKeyboardButton("📝 Ajouter une note", callback_data=f"annoter_pwa_{topic_id}")
    )

    await bot.edit_message_text(
        chat_id=STAFF_GROUP_ID,
        message_id=message.reply_to_message.message_id if message.reply_to_message else message.message_id,
        text=panel_text,
        reply_markup=kb
    )

    await message.reply("✅ Note PWA enregistrée et panel mis à jour.")

# ========== CHOIX DANS LE MENU INLINE ==========

@dp.callback_query_handler(lambda call: call.data == "vip_message_gratuit")
async def choix_type_message_vip(call: types.CallbackQuery):
    await call.answer()
    admin_id = call.from_user.id

    # On ne garde que le mode "en_attente_message" = gratuit
    admin_modes[admin_id] = "en_attente_message"

    await bot.send_message(
        chat_id=admin_id,
        text="✍️ Envoie maintenant le message (texte/photo/vidéo) à diffuser GRATUITEMENT à tous tes VIPs."
    )


# ========== TRAITEMENT MESSAGE GROUPÉ GRATUIT ==========

async def traiter_message_groupé(message: types.Message, admin_id=None):
    admin_id = admin_id or message.from_user.id

    if message.text:
        pending_mass_message[admin_id] = {"type": "text", "content": message.text}
        preview = message.text

    elif message.photo:
        pending_mass_message[admin_id] = {
            "type": "photo",
            "content": message.photo[-1].file_id,
            "caption": message.caption or ""
        }
        preview = f"[Photo] {message.caption or ''}"

    elif message.video:
        pending_mass_message[admin_id] = {
            "type": "video",
            "content": message.video.file_id,
            "caption": message.caption or ""
        }
        preview = f"[Vidéo] {message.caption or ''}"

    elif message.audio:
        pending_mass_message[admin_id] = {
            "type": "audio",
            "content": message.audio.file_id,
            "caption": message.caption or ""
        }
        preview = f"[Audio] {message.caption or ''}"

    elif message.voice:
        pending_mass_message[admin_id] = {
            "type": "voice",
            "content": message.voice.file_id
        }
        preview = "[Note vocale]"

    else:
        await message.reply("❌ Message non supporté.")
        return

    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton("✅ Confirmer l’envoi", callback_data="confirmer_envoi_groupé"),
        InlineKeyboardButton("📅 Programmer l’envoi", callback_data="programmer_envoi_groupé"),
        InlineKeyboardButton("❌ Annuler l’envoi", callback_data="annuler_envoi_groupé")
    )
    await message.reply(f"Prévisualisation :\n\n{preview}", reply_markup=kb)



# ========== CALLBACKS ENVOI / ANNULATION GROUPÉ ==========

# 100
@dp.callback_query_handler(lambda call: call.data == "programmer_envoi_groupé")
async def programmer_envoi_groupé(call: types.CallbackQuery):
    await call.answer()
    admin_id = call.from_user.id

    message_data = pending_mass_message.get(admin_id)
    if not message_data:
        await bot.send_message(
            chat_id=admin_id,
            text="❌ Aucun message en attente à programmer."
        )
        return

    # 1) On demande d'abord le jour
    kb = InlineKeyboardMarkup(row_width=2)
    for jour in ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche"]:
        kb.insert(
            InlineKeyboardButton(jour, callback_data=f"prog_jour_{jour.lower()}")
        )

    kb.add(InlineKeyboardButton("❌ Annuler", callback_data="annuler_envoi_groupé"))

    await bot.send_message(
        chat_id=admin_id,
        text="🗓 Choisis le jour d’envoi pour ce message :",
        reply_markup=kb
    )

# 100
# 100
@dp.callback_query_handler(lambda call: call.data.startswith("prog_jour_"))
async def choisir_jour_programmation(call: types.CallbackQuery):
    await call.answer()
    admin_id = call.from_user.id

    jour_code = call.data.replace("prog_jour_", "")  # 'lundi'
    jour_label = jour_code.capitalize()              # 'Lundi'

    if jour_label not in JOUR_TO_WEEKDAY:
        await bot.send_message(
            chat_id=admin_id,
            text="❌ Jour invalide, recommence."
        )
        return

    # On mémorise le jour choisi pour cet admin
    pending_programmation[admin_id] = {"jour": jour_label}

    # On passe en mode "en_attente_heure_prog"
    admin_modes[admin_id] = "en_attente_heure_prog"

    await bot.send_message(
        chat_id=admin_id,
        text=(
            f"⏰ À quelle heure veux-tu envoyer ce message le {jour_label} ?\n\n"
            "Format 24h, par ex : `10:00` ou `21:30`."
        ),
        parse_mode="Markdown"
    )

# 100

def get_due_programmations():
    """
    Récupère les programmations avec Status='pending'
    et dont RunAtUTC est passée (<= maintenant UTC).
    Retourne une liste de records Airtable complets.
    """
    if AIRTABLE_API_KEY is None or BASE_ID is None:
        raise RuntimeError("AIRTABLE_API_KEY ou BASE_ID non configuré")

    url = f"https://api.airtable.com/v0/{BASE_ID}/{AIRTABLE_TABLE_PROGRAMMATIONS.replace(' ', '%20')}"
    headers = {
        "Authorization": f"Bearer {AIRTABLE_API_KEY}",
    }

    # On filtre côté Airtable sur Status = 'pending'
    params = {
        "filterByFormula": "{Status}='pending'",
        "pageSize": 100,  # on limite à 100 par batch
    }

    resp = requests.get(url, headers=headers, params=params)
    data = resp.json()

    if resp.status_code >= 300:
        raise RuntimeError(f"Airtable error {resp.status_code}: {data}")

    now_utc = datetime.now(timezone.utc)
    due_records = []

    for record in data.get("records", []):
        fields = record.get("fields", {})
        run_at_str = fields.get("RunAtUTC")

        if not run_at_str:
            continue

        # Support des deux formats : ...Z ou avec offset
        try:
            if run_at_str.endswith("Z"):
                run_at_dt = datetime.fromisoformat(run_at_str.replace("Z", "+00:00"))
            else:
                run_at_dt = datetime.fromisoformat(run_at_str)
        except Exception as e:
            print(f"[SCHEDULE] RunAtUTC invalide pour record {record.get('id')}: {e}")
            continue

        # Si la date/heure est passée → on ajoute
        if run_at_dt <= now_utc:
            due_records.append(record)

    return due_records
#101
#101
def mark_programmation_as_sent(record_id):
    """
    Met à jour Status='sent' et SentAt=now UTC pour une programmation.
    """
    if AIRTABLE_API_KEY is None or BASE_ID is None:
        raise RuntimeError("AIRTABLE_API_KEY ou BASE_ID non configuré")

    url = f"https://api.airtable.com/v0/{BASE_ID}/{AIRTABLE_TABLE_PROGRAMMATIONS.replace(' ', '%20')}/{record_id}"

    now_utc = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    fields = {
        "Status": "sent",
        "SentAt": now_utc,
    }

    headers = {
        "Authorization": f"Bearer {AIRTABLE_API_KEY}",
        "Content-Type": "application/json",
    }

    resp = requests.patch(url, headers=headers, json={"fields": fields})
    data = resp.json()

    if resp.status_code >= 300:
        raise RuntimeError(f"Airtable error {resp.status_code}: {data}")

    return data

#101
#101
async def process_due_programmations_once():
    """
    1. Récupère les programmations dues (pending + RunAtUTC <= now)
    2. Pour chacune, envoie le message à tous les VIPs
    3. Marque la programmation comme sent
    """
    try:
        due_records = get_due_programmations()
    except Exception as e:
        print(f"[SCHEDULE] Erreur en récupérant les programmations dues : {e}")
        return

    if not due_records:
        return  # rien à faire

    # On récupère les VIPs de CE bot (on réutilise ta logique)
    try:
        # Ici on part du principe que ce bot a un seul "admin vendeur"
        # et que SELLER_EMAIL correspond à la table VIP de ce bot.
        vip_ids = list(get_vip_ids_for_admin_email(SELLER_EMAIL))
    except Exception as e:
        print(f"[SCHEDULE] Erreur en récupérant les VIPs pour {SELLER_EMAIL} : {e}")
        return

    if not vip_ids:
        print("[SCHEDULE] Aucun VIP trouvé, envoi annulé.")
        return

    for record in due_records:
        record_id = record.get("id")
        fields = record.get("fields", {})

        msg_type = fields.get("Type")
        content = fields.get("Content")
        caption = fields.get("Caption", "")

        if not msg_type or not content:
            print(f"[SCHEDULE] Record {record_id} incomplet, skip.")
            continue

        envoyes = 0
        erreurs = 0

        for vip in vip_ids:
            try:
                vip_int = int(vip)

                if msg_type == "text":
                    await bot.send_message(chat_id=vip_int, text=content)

                elif msg_type == "photo":
                    await bot.send_photo(chat_id=vip_int, photo=content, caption=caption)

                elif msg_type == "video":
                    await bot.send_video(chat_id=vip_int, video=content, caption=caption)

                elif msg_type == "audio":
                    await bot.send_audio(chat_id=vip_int, audio=content, caption=caption)

                elif msg_type == "voice":
                    await bot.send_voice(chat_id=vip_int, voice=content)

                elif msg_type == "document":
                    await bot.send_document(chat_id=vip_int, document=content, caption=caption)

                else:
                    print(f"[SCHEDULE] Type inconnu '{msg_type}' pour record {record_id}")
                    erreurs += 1
                    continue

                envoyes += 1

            except Exception as e:
                print(f"[SCHEDULE] Erreur envoi VIP {vip}: {e}")
                erreurs += 1

        print(f"[SCHEDULE] Programmation {record_id} envoyée à {envoyes} VIP(s), erreurs={erreurs}")

        try:
            mark_programmation_as_sent(record_id)
        except Exception as e:
            print(f"[SCHEDULE] Erreur mise à jour Status pour {record_id}: {e}")
        
        # 🔔 Notification au Directeur
        try:
            jour = fields.get("Jour", "—")
            heure_locale = fields.get("Heure locale", "—")

            notif_text = (
                "📤 *Programmation envoyée*\n\n"
                f"• ID : `{record_id}`\n"
                f"• Jour : *{jour}*\n"
                f"• Heure locale : *{heure_locale}*\n"
                f"• Type : *{msg_type}*\n"
                f"• VIPs touchés : *{envoyes}*\n"
                f"• Erreurs : *{erreurs}*\n\n"
                "Statut : *sent* dans Airtable ✅"
            )

            await bot.send_message(
                chat_id=DIRECTEUR_ID,
                text=notif_text,
                parse_mode="Markdown"
            )
        except Exception as e:
            print(f"[SCHEDULE] Erreur envoi notification Directeur pour {record_id}: {e}")
#101

import asyncio
from datetime import datetime, timezone
# ... (le reste de tes imports)

async def scheduler_loop():
    """
    Boucle qui tourne en tâche de fond.
    Toutes les 60s, elle tente d'envoyer les programmations dues.
    """
    print("[SCHEDULE] Scheduler démarré.")
    while True:
        try:
            now_utc = datetime.now(timezone.utc).isoformat()
            print(f"[SCHEDULE] Tick - vérification des programmations à {now_utc}")
            await process_due_programmations_once()
            print("[SCHEDULE] Tick terminé.")
        except Exception as e:
            import traceback
            traceback.print_exc()
            print(f"[SCHEDULE] Erreur dans scheduler_loop : {e}")
        await asyncio.sleep(60)


#101


@dp.callback_query_handler(lambda call: call.data == "confirmer_envoi_groupé")
async def confirmer_envoi_groupé(call: types.CallbackQuery):
    await call.answer()
    admin_id = call.from_user.id
    message_data = pending_mass_message.get(admin_id)

    if not message_data:
        await call.message.edit_text("❌ Aucun message en attente à envoyer.")
        return

    # 1️⃣ Récupérer l'e-mail de cet admin
    email = ADMIN_EMAILS.get(admin_id)
    if not email:
        await bot.send_message(
            chat_id=admin_id,
            text="❌ Ton e-mail admin n’est pas configuré dans le bot. Parle à Nova Pulse pour le mettre à jour."
        )
        pending_mass_message.pop(admin_id, None)
        return

    # 2️⃣ Récupérer les VIPs de CET admin via Airtable
    try:
        vip_ids = list(get_vip_ids_for_admin_email(email))  # 🔹 helper à ajouter à côté de /stat
    except Exception as e:
        print(f"[MASS_VIP] Erreur en récupérant les VIPs pour {email} : {e}")
        await bot.send_message(
            chat_id=admin_id,
            text="❌ Impossible de récupérer la liste de tes VIPs pour le moment."
        )
        pending_mass_message.pop(admin_id, None)
        return

    if not vip_ids:
        await bot.send_message(
            chat_id=admin_id,
            text="ℹ️ Aucun VIP trouvé pour toi. Rien à envoyer."
        )
        pending_mass_message.pop(admin_id, None)
        return

    await bot.send_message(
        chat_id=admin_id,
        text=f"⏳ Envoi du message à {len(vip_ids)} VIP(s)..."
    )

    envoyes = 0
    erreurs = 0

    # 3️⃣ Envoi 100 % GRATUIT à ces VIPs
    for vip_id in vip_ids:
        try:
            vip_id = int(vip_id)

            if message_data["type"] == "text":
                await bot.send_message(chat_id=vip_id, text=message_data["content"])

            elif message_data["type"] == "photo":
                await bot.send_photo(
                    chat_id=vip_id,
                    photo=message_data["content"],
                    caption=message_data.get("caption", "")
                )

            elif message_data["type"] == "video":
                await bot.send_video(
                    chat_id=vip_id,
                    video=message_data["content"],
                    caption=message_data.get("caption", "")
                )

            elif message_data["type"] == "audio":
                await bot.send_audio(
                    chat_id=vip_id,
                    audio=message_data["content"],
                    caption=message_data.get("caption", "")
                )

            elif message_data["type"] == "voice":
                await bot.send_voice(
                    chat_id=vip_id,
                    voice=message_data["content"]
                )

            envoyes += 1

        except Exception as e:
            print(f"❌ Erreur envoi à {vip_id} : {e}")
            erreurs += 1

    await bot.send_message(
        chat_id=admin_id,
        text=f"✅ Envoyé à {envoyes} VIP(s).\n⚠️ Échecs : {erreurs}"
    )
    pending_mass_message.pop(admin_id, None)


@dp.callback_query_handler(lambda call: call.data == "annuler_envoi_groupé")
async def annuler_envoi_groupé(call: types.CallbackQuery):
    await call.answer("❌ Envoi annulé.")
    admin_id = call.from_user.id
    pending_mass_message.pop(admin_id, None)
    await call.message.edit_text("❌ Envoi annulé.")



#mettre le tableau de vips
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

    # Étape 1 : repérer les pseudos ayant AU MOINS un paiement > 0 (Type acces = paiement ou vip)
    pseudos_vip = set()
    for r in records:
        f = r.get("fields", {})
        pseudo = (f.get("Pseudo Telegram", "") or "").strip()
        type_acces = (f.get("Type acces", "") or "").strip().lower()
        montant_raw = f.get("Montant")

        try:
            montant = float(montant_raw or 0)
        except Exception:
            montant = 0.0

        if pseudo and montant > 0 and type_acces in ("paiement", "vip"):
            pseudos_vip.add(pseudo)

    if not pseudos_vip:
        await bot.send_message(telegram_id, "📭 Tu n'as encore aucun client VIP (aucun paiement enregistré).")
        return

    # Étape 2 : additionner TOUS les montants (Paiement + VIP) de ces pseudos uniquement
    montants_par_pseudo = {}
    for r in records:
        f = r.get("fields", {})
        pseudo = (f.get("Pseudo Telegram", "") or "").strip()
        montant_raw = f.get("Montant")

        if not pseudo or pseudo not in pseudos_vip:
            continue

        try:
            montant_float = float(montant_raw or 0)
        except Exception:
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

        await bot.send_message(telegram_id, message, parse_mode="Markdown")

    except Exception as e:
        import traceback
        error_text = traceback.format_exc()
        print("❌ ERREUR DANS VIPS + TOP 3 :\n", error_text)
        await bot.send_message(telegram_id, "❌ Une erreur est survenue lors de l'affichage des VIPs.")


#fin du 19 juillet 2025 mettre le tableau de vips
