# vip_topics.py

import os
import json
import requests  # pour appeler l'API Airtable
from aiogram import types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from core import bot, authorized_users

# ID du supergroupe staff (forum) où se trouvent les topics VIP
STAFF_GROUP_ID = int(os.getenv("STAFF_GROUP_ID", "0"))

# Fichier pour persister les topics (annotations, panneau, etc.)
VIP_TOPICS_FILE = "vip_topics.json"

# Mémoire en RAM :
#   user_id -> {"topic_id": int, "panel_message_id": int, "note": str, "admin_id": int, "admin_name": str, ...}
_user_topics = {}
#   topic_id -> user_id
_topic_to_user = {}

# ====== CONFIG AIRTABLE PRINCIPAL (paiements / VIP / Topic ID) ======
AIRTABLE_API_KEY = os.getenv("AIRTABLE_API_KEY")
BASE_ID = os.getenv("BASE_ID")
TABLE_NAME = os.getenv("TABLE_NAME")
# ============================================================

# ====== CONFIG AIRTABLE ANNOTATIONS (nouvelle table) ======
ANNOT_API_KEY = os.getenv("ANNOT_API_KEY") or AIRTABLE_API_KEY
ANNOT_BASE_ID = os.getenv("ANNOT_BASE_ID", BASE_ID)
ANNOT_TABLE_NAME = os.getenv("ANNOT_TABLE_NAME")  # doit être défini pour activer la sync
# =========================================================


def save_vip_topics():
    """
    Sauvegarde _user_topics dans le fichier JSON.
    Sert de persistance locale pour :
      - topic_id (en secours)
      - panel_message_id
      - note
      - admin_id
      - admin_name
    """
    data = {str(user_id): d for user_id, d in _user_topics.items()}
    try:
        with open(VIP_TOPICS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"[VIP_TOPICS] Sauvegarde JSON : {len(data)} topics enregistrés.")
    except Exception as e:
        print(f"[VIP_TOPICS] Erreur lors de la sauvegarde JSON : {e}")


def load_vip_topics_from_disk():
    """
    Recharge depuis vip_topics.json UNIQUEMENT les infos d'annotation :
        - panel_message_id
        - note
        - admin_id
        - admin_name
    Sans écraser les topic_id déjà chargés depuis Airtable.
    Si un user_id n'existe pas encore en mémoire, on recrée une entrée propre.
    """
    try:
        with open(VIP_TOPICS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)

        merged = 0

        for user_id_str, d in data.items():
            try:
                user_id = int(user_id_str)
            except Exception:
                continue

            existing = _user_topics.get(user_id)

            # FIX MERGE TOPIC ID
            stored_topic = d.get("topic_id")
            existing_topic = existing.get("topic_id") if existing else None
            topic_to_use = stored_topic if stored_topic else existing_topic

            if not existing:
                existing = {
                    "topic_id": topic_to_use,
                    "panel_message_id": d.get("panel_message_id"),
                    "note": d.get("note", ""),
                    "admin_id": d.get("admin_id"),
                    "admin_name": d.get("admin_name", "Aucun"),
                }
            else:
                if "panel_message_id" in d:
                    existing["panel_message_id"] = d["panel_message_id"]
                if "note" in d:
                    existing["note"] = d["note"]
                if "admin_id" in d:
                    existing["admin_id"] = d["admin_id"]
                if "admin_name" in d:
                    existing["admin_name"] = d["admin_name"]

                existing["topic_id"] = topic_to_use

            _user_topics[user_id] = existing

            # Map inverse uniquement si topic valide
            if topic_to_use:
                _topic_to_user[topic_to_use] = user_id

            merged += 1

        print(f"[VIP_TOPICS] Annotations restaurées depuis JSON pour {merged} VIP(s).")

    except FileNotFoundError:
        print("[VIP_TOPICS] Aucun fichier vip_topics.json à charger (normal si première exécution).")
    except Exception as e:
        print(f"[VIP_TOPICS] Erreur au chargement des annotations depuis JSON : {e}")




# ============================================================
# ========== CREATION TOPIC + PANEL REFACTO (FIX) ============
# ============================================================

async def create_topic_and_panel(user: types.User) -> int:
    """
    Création d'un nouveau topic + panneau admin.
    Utilisé lors de la première création ou recréation auto.
    """
    user_id = user.id
    title = f"VIP {user.username or user.first_name or str(user_id)}"

    try:
        res = await bot.request(
            "createForumTopic",
            {
                "chat_id": STAFF_GROUP_ID,
                "name": title
            }
        )
    except Exception as e:
        print(f"[VIP_TOPICS] ERREUR createForumTopic pour {user_id} : {e}")
        return 0

    topic_id = res.get("message_thread_id")
    if not topic_id:
        print(f"[VIP_TOPICS] Pas de message_thread_id dans la réponse pour {user_id} : {res}")
        return 0

    # Panneau
    kb = InlineKeyboardMarkup()
    kb.add(
        InlineKeyboardButton("✅ Prendre en charge", callback_data=f"prendre_{user_id}"),
        InlineKeyboardButton("📝 Ajouter une note", callback_data=f"annoter_{user_id}")
    )

    panel_text = (
        "🧐 PANEL DE CONTRÔLE VIP\n\n"
        f"👤 Client : {user.username or user.first_name or str(user_id)}\n"
        "📒 Notes : \n"
        "👤 Admin en charge : Aucun"
    )

    panel_message_id = None
    try:
        panel_res = await bot.request(
            "sendMessage",
            {
                "chat_id": STAFF_GROUP_ID,
                "text": panel_text,
                "message_thread_id": topic_id,
                "reply_markup": kb
            }
        )
        panel_message_id = panel_res.get("message_id")
    except Exception as e:
        print(f"[VIP_TOPICS] Erreur envoi panneau pour {user_id} : {e}")

    # Sauvegarde en mémoire
    _user_topics[user_id] = {
        "topic_id": topic_id,
        "panel_message_id": panel_message_id,
        "note": "",
        "admin_id": None,
        "admin_name": "Aucun",
    }
    _topic_to_user[topic_id] = user_id
    save_vip_topics()

    return topic_id



async def ensure_topic_for_vip(user: types.User) -> int:
    """
    Vérifie / crée le topic pour un utilisateur.
    - Si déjà en mémoire → renvoie le topic existant.
    - Sinon → crée un topic, un panneau de contrôle,
      sauvegarde en JSON.
    - La synchro Airtable du Topic ID ne se fait QUE si l'user est VIP (dans authorized_users).
    """
    user_id = user.id
    print(f"[VIP_TOPICS] ensure_topic_for_vip() appelé pour user_id={user_id}")

    # Topic déjà existant pour ce user en mémoire
        # FIX : user connu mais topic vide = correction auto
        # Topic déjà existant pour ce user en mémoire
    if user_id in _user_topics:
        topic_id = _user_topics[user_id].get("topic_id")

        # PROTECTION : si l'entrée existe mais avec None/0 => recréation
        if not topic_id:
            print(f"[VIP_TOPICS] {user_id} présent sans topic valide → recréation forcée.")
            topic_id = await create_topic_and_panel(user)
            if user_id in authorized_users:
                # sync Airtable ici si tu veux
                pass
            return topic_id

        print(f"[VIP_TOPICS] Topic déjà connu pour {user_id} -> {topic_id}")
        return topic_id


    title = f"VIP {user.username or user.first_name or str(user_id)}"

    # Création du topic dans le forum staff
    try:
        res = await bot.request(
            "createForumTopic",
            {
                "chat_id": STAFF_GROUP_ID,
                "name": title
            }
        )
    except Exception as e:
        print(f"[VIP_TOPICS] ERREUR createForumTopic pour {user_id} : {e}")
        return 0

    topic_id = res.get("message_thread_id")
    if topic_id is None:
        print(f"[VIP_TOPICS] Pas de message_thread_id dans la réponse pour {user_id} : {res}")
        return 0

    print(f"[VIP_TOPICS] Nouveau topic créé pour {user_id} dans {STAFF_GROUP_ID} -> topic_id={topic_id}")

    _topic_to_user[topic_id] = user_id

    # Clavier du panneau de contrôle
    kb = InlineKeyboardMarkup()
    kb.add(
        InlineKeyboardButton("✅ Prendre en charge", callback_data=f"prendre_{user_id}"),
        InlineKeyboardButton("📝 Ajouter une note", callback_data=f"annoter_{user_id}")
    )

    panel_text = (
        "🧐 PANEL DE CONTRÔLE VIP\n\n"
        f"👤 Client : {user.username or user.first_name or str(user_id)}\n"
        "📒 Notes : \n"
        "👤 Admin en charge : Aucun"
    )

    panel_message_id = None
    try:
        panel_res = await bot.request(
            "sendMessage",
            {
                "chat_id": STAFF_GROUP_ID,
                "text": panel_text,
                "message_thread_id": topic_id,
                "reply_markup": kb
            }
        )
        panel_message_id = panel_res.get("message_id")
        print(f"[VIP_TOPICS] Panneau de contrôle envoyé pour {user_id} → msg_id={panel_message_id}")
    except Exception as e:
        print(f"[VIP_TOPICS] Erreur envoi panneau de contrôle dans topic {topic_id} : {e}")

    # On initialise l'entrée avec topic + panneau, sans note ni admin pour l'instant
    _user_topics[user_id] = {
        "topic_id": topic_id,
        "panel_message_id": panel_message_id,
        "note": "",
        "admin_id": None,
        "admin_name": "Aucun",
    }
    # Sauvegarde JSON
    save_vip_topics()

    # ⚠️ IMPORTANT :
    # - TOUS les clients ont un topic (VIP ou non)
    # - MAIS on ne synchronise le Topic ID dans Airtable QUE pour les vrais VIP (payeurs),
    #   identifiés par authorized_users.
    if user_id not in authorized_users:
        print(f"[VIP_TOPICS] User {user_id} non VIP : topic {topic_id} créé en local (pas de sync Airtable).")
        return topic_id

    # ===== Enregistrement / mise à jour du Topic ID dans le Airtable principal =====
    try:
        if AIRTABLE_API_KEY and BASE_ID and TABLE_NAME:
            url_base = f"https://api.airtable.com/v0/{BASE_ID}/{TABLE_NAME.replace(' ', '%20')}"
            headers = {
                "Authorization": f"Bearer {AIRTABLE_API_KEY}",
                "Content-Type": "application/json"
            }

            # On cherche la/les lignes correspondant à ce user_id ET Type acces = VIP
            params = {
                "filterByFormula": f"AND({{ID Telegram}} = '{user_id}', {{Type acces}} = 'VIP')"
            }
            r = requests.get(url_base, headers=headers, params=params)
            r.raise_for_status()
            records = r.json().get("records", [])

            if not records:
                # Aucun VIP trouvé pour cet ID → on crée une ligne dédiée au Topic ID
                data = {
                    "fields": {
                        "ID Telegram": str(user_id),
                        "Type acces": "VIP",
                        "Montant": 0,
                        "Contenu": "Création Topic VIP automatique",
                        "Topic ID": str(topic_id),  # en string
                    }
                }
                pr = requests.post(url_base, json=data, headers=headers)
                if pr.status_code != 200:
                    print(f"[VIP_TOPICS] Erreur POST Topic ID Airtable pour user {user_id}: {pr.text}")
                else:
                    print(f"[VIP_TOPICS] Topic ID {topic_id} CRÉÉ dans Airtable pour user {user_id}")
            else:
                # On met à jour toutes les lignes VIP existantes pour ce user
                for rec in records:
                    rec_id = rec["id"]
                    patch_url = f"{url_base}/{rec_id}"
                    data = {"fields": {"Topic ID": str(topic_id)}}  # en string
                    pr = requests.patch(patch_url, json=data, headers=headers)
                    if pr.status_code != 200:
                        print(f"[VIP_TOPICS] Erreur PATCH Topic ID Airtable pour user {user_id}: {pr.text}")
                    else:
                        print(f"[VIP_TOPICS] Topic ID {topic_id} enregistré dans Airtable pour user {user_id}")
        else:
            print("[VIP_TOPICS] Variables Airtable manquantes, impossible d'enregistrer Topic ID.")
    except Exception as e:
        print(f"[VIP_TOPICS] Erreur mise à jour Airtable Topic ID pour user {user_id} : {e}")
    # ====================================================

    return topic_id


def is_vip(user_id: int) -> bool:
    """
    VIP = client PAYEUR → présent dans authorized_users.
    (Les topics existent aussi pour les non-VIP, donc on ne se base plus sur _user_topics.)
    """
    return user_id in authorized_users


def get_user_id_by_topic_id(topic_id: int):
    return _topic_to_user.get(topic_id)


def get_panel_message_id_by_user(user_id: int):
    data = _user_topics.get(user_id)
    if not data:
        return None
    return data.get("panel_message_id")


async def load_vip_topics():
    """
    Ancienne version async de chargement depuis le JSON (plus vraiment utilisée).
    Gardée pour compatibilité éventuelle.
    """
    try:
        with open(VIP_TOPICS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            for user_id_str, d in data.items():
                if "topic_id" in d:
                    user_id = int(user_id_str)
                    _user_topics[user_id] = d
                    _topic_to_user[d["topic_id"]] = user_id
                    print(f"[VIP_TOPICS] Topic restauré (JSON) : user_id={user_id} -> topic_id={d['topic_id']}")
    except FileNotFoundError:
        print("[VIP_TOPICS] Aucun fichier de topics à charger.")
    except Exception as e:
        print(f"[VIP_TOPICS] Erreur au chargement des topics (JSON) : {e}")


def update_vip_info(user_id: int, note: str = None, admin_id: int = None, admin_name: str = None):
    """
    Met à jour les infos VIP (note, admin en charge) pour un user_id.
    Retourne le dict complet pour ce user_id.
    """
    if user_id not in _user_topics:
        _user_topics[user_id] = {}

    data = _user_topics[user_id]

    changed = False

    if note is not None:
        old = data.get("note")

        # Si une note existe déjà, on ajoute la nouvelle en dessous
        if old:
            data["note"] = f"{old}\n{note}"
        else:
            data["note"] = note

        changed = True


    if admin_id is not None:
        data["admin_id"] = admin_id
        changed = True

    if admin_name is not None:
        data["admin_name"] = admin_name
        changed = True

    _user_topics[user_id] = data
    # Sauvegarde JSON à chaque modification
    save_vip_topics()

    # Si la configuration ANNOT_TABLE_NAME existe, sauvegarder aussi dans Airtable (upsert)
    if changed and ANNOT_TABLE_NAME:
        try:
            save_annotation_to_airtable(user_id, data.get("note", ""), data.get("admin_name", "Aucun"))
        except Exception as e:
            print(f"[ANNOTATION] Erreur sauvegarde Airtable dans update_vip_info : {e}")

    return data

# ========= IMPORT TOPICS DEPUIS AIRTABLE (TOUS LES USERS AVEC TOPIC ID) =========

async def load_vip_topics_from_airtable():
    """
    Recharge tous les Topic ID existants depuis Airtable
    afin d'éviter toute recréation de topic après redéploiement.
    Chaque utilisateur ayant déjà un Topic ID conserve son historique.
    """

    if not (AIRTABLE_API_KEY and BASE_ID and TABLE_NAME):
        print("[VIP_TOPICS] Variables Airtable manquantes, impossible de charger les topics.")
        return

    url = f"https://api.airtable.com/v0/{BASE_ID}/{TABLE_NAME.replace(' ', '%20')}"
    headers = {"Authorization": f"Bearer {AIRTABLE_API_KEY}"}

    # ✅ On charge TOUTES les lignes ayant déjà un Topic ID
    params = {
        "filterByFormula": "NOT({Topic ID}=BLANK())"
    }

    response = requests.get(url, headers=headers, params=params)
    data = response.json()

    count = 0

    for record in data.get("records", []):
        fields = record.get("fields", {})

        user_id = fields.get("ID Telegram")
        topic_id = fields.get("Topic ID")

        if user_id and topic_id:
            _user_topics[int(user_id)] = int(topic_id)
            _topic_to_user[int(topic_id)] = int(user_id)
            count += 1

    print(f"[VIP_TOPICS] {count} topics rechargés depuis Airtable.")


    try:
        resp = requests.get(url, headers=headers, params=params)
        resp.raise_for_status()
        records = resp.json().get("records", [])

        loaded = 0
        for rec in records:
            f = rec.get("fields", {})
            topic_id = f.get("Topic ID")
            telegram_id = f.get("ID Telegram")

            if not topic_id or not telegram_id:
                continue

            try:
                topic_id_int = int(topic_id)
                telegram_id_int = int(telegram_id)
            except Exception:
                continue

            _user_topics[telegram_id_int] = {
                "topic_id": topic_id_int,
                "panel_message_id": None,
                "note": "",
                "admin_id": None,
                "admin_name": "Aucun",
            }
            _topic_to_user[topic_id_int] = telegram_id_int
            loaded += 1

        print(f"[VIP_TOPICS] {loaded} Topic IDs chargés depuis Airtable.")

    except Exception as e:
        print(f"[VIP_TOPICS] Erreur import topics Airtable : {e}")

# ========= FIN IMPORT TOPICS DEPUIS AIRTABLE =========


# ========= ANNOTATIONS AIRTABLE (NEW) =========

def _annot_table_base_url():
    """URL de base pour la table Annotations (URI encoded table name)"""
    if not (ANNOT_API_KEY and ANNOT_BASE_ID and ANNOT_TABLE_NAME):
        return None
    return f"https://api.airtable.com/v0/{ANNOT_BASE_ID}/{ANNOT_TABLE_NAME.replace(' ', '%20')}"


def save_annotation_to_airtable(user_id: int, note: str, admin: str) -> bool:
    """
    Upsert une annotation dans la table ANNOT_TABLE_NAME.
    Colonnes attendues : "ID Telegram", "Note", "Admin"
    """
    base_url = _annot_table_base_url()
    api_key = ANNOT_API_KEY
    if not base_url or not api_key:
        print("[ANNOTATION] Variables Airtable annotations manquantes, skip save.")
        return False

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    # Cherche un enregistrement existant pour cet ID Telegram
    try:
        params = {"filterByFormula": f"{{ID Telegram}} = '{user_id}'"}
        r = requests.get(base_url, headers=headers, params=params)
        r.raise_for_status()
        records = r.json().get("records", [])
    except Exception as e:
        print(f"[ANNOTATION] Erreur recherche annotation Airtable pour user {user_id} : {e}")
        return False

    fields = {
        "ID Telegram": str(user_id),
        "Note": note or "",
        "Admin": admin or ""
    }

    try:
        if records:
            # PATCH le premier record trouvé (on suppose une ligne par user)
            rec_id = records[0]["id"]
            patch_url = f"{base_url}/{rec_id}"
            pr = requests.patch(patch_url, json={"fields": fields}, headers=headers)
            if pr.status_code not in (200, 201):
                print(f"[ANNOTATION] Erreur PATCH Annotation Airtable pour user {user_id}: {pr.status_code} {pr.text}")
                return False
            print(f"[ANNOTATION] Annotation mise à jour Airtable pour user {user_id} (rec {rec_id}).")
            return True
        else:
            # Crée un nouveau record
            pr = requests.post(base_url, json={"fields": fields}, headers=headers)
            if pr.status_code not in (200, 201):
                print(f"[ANNOTATION] Erreur POST Annotation Airtable pour user {user_id}: {pr.status_code} {pr.text}")
                return False
            print(f"[ANNOTATION] Annotation créée Airtable pour user {user_id}.")
            return True
    except Exception as e:
        print(f"[ANNOTATION] Exception lors de save_annotation_to_airtable pour user {user_id}: {e}")
        return False


def load_annotations_from_airtable():
    """
    Charge toutes les annotations depuis la table ANNOT_TABLE_NAME
    et les merge dans _user_topics (champ note/admin).
    """
    base_url = _annot_table_base_url()
    api_key = ANNOT_API_KEY
    if not base_url or not api_key:
        print("[ANNOTATION] Variables Airtable annotations manquantes, skip load.")
        return

    headers = {"Authorization": f"Bearer {api_key}"}
    try:
        r = requests.get(base_url, headers=headers)
        r.raise_for_status()
        records = r.json().get("records", [])
    except Exception as e:
        print(f"[ANNOTATION] Échec chargement Airtable : {e}")
        return

    loaded = 0
    for rec in records:
        f = rec.get("fields", {})
        telegram_id = f.get("ID Telegram")
        note = f.get("Note")
        admin = f.get("Admin")

        if not telegram_id:
            continue
        try:
            telegram_id_int = int(telegram_id)
        except Exception:
            continue

        existing = _user_topics.get(telegram_id_int, {})
        # Conserver topic_id/panel si présents
        existing.setdefault("topic_id", existing.get("topic_id"))
        existing.setdefault("panel_message_id", existing.get("panel_message_id"))
        existing["note"] = note or ""
        existing["admin_id"] = existing.get("admin_id")  # admin_id not stored in Airtable, keep existing
        existing["admin_name"] = admin or "Aucun"

        _user_topics[telegram_id_int] = existing
        loaded += 1

    print(f"[ANNOTATION] {loaded} annotations chargées depuis Airtable.")


# ========= FIN ANNOTATIONS AIRTABLE =========


async def restore_missing_panels():
    """
    Après chargement via Airtable + fusion JSON, recrée un panneau de contrôle
    pour chaque VIP qui a un topic_id mais pas de panel_message_id.
    Utilise la note et l'admin_name si disponibles.
    """
    restored = 0

    for user_id, info in list(_user_topics.items()):
        topic_id = info.get("topic_id")
        panel_message_id = info.get("panel_message_id")

        if not topic_id:
            continue
        if panel_message_id:
            # On suppose que le panneau existe encore
            continue

        note = info.get("note", "")
        admin_name = info.get("admin_name", "Aucun")

        kb = InlineKeyboardMarkup()
        kb.add(
            InlineKeyboardButton("✅ Prendre en charge", callback_data=f"prendre_{user_id}"),
            InlineKeyboardButton("📝 Ajouter une note", callback_data=f"annoter_{user_id}")
        )

        panel_text = (
            "🧐 PANEL DE CONTRÔLE VIP\n\n"
            f"👤 Client : {user_id}\n"
            f"📒 Notes : {note}\n"
            f"👤 Admin en charge : {admin_name}"
        )

        try:
            panel_res = await bot.request(
                "sendMessage",
                {
                    "chat_id": STAFF_GROUP_ID,
                    "text": panel_text,
                    "message_thread_id": topic_id,
                    "reply_markup": kb
                }
            )
            new_panel_id = panel_res.get("message_id")
            info["panel_message_id"] = new_panel_id
            _user_topics[user_id] = info
            restored += 1
            print(f"[VIP_TOPICS] Panneau restauré pour user_id={user_id} dans topic_id={topic_id}, msg_id={new_panel_id}")
        except Exception as e:
            print(f"[VIP_TOPICS] Erreur restauration panneau de contrôle pour user_id={user_id} : {e}")

    if restored > 0:
        # On persiste les nouveaux panel_message_id
        save_vip_topics()

    print(f"[VIP_TOPICS] Panneaux restaurés pour {restored} VIP(s).")
