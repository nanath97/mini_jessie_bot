# vip_topics.py

import os
import json
import requests
from aiogram import types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from core import bot, authorized_users
import os



# =========================================================
# CONFIG
# =========================================================

STAFF_GROUP_ID = int(os.getenv("STAFF_GROUP_ID", "0"))

VIP_TOPICS_FILE = "vip_topics.json"  # fallback local (Render peut le perdre)

AIRTABLE_API_KEY = os.getenv("AIRTABLE_API_KEY")
BASE_ID = os.getenv("BASE_ID")
TABLE_NAME = os.getenv("TABLE_NAME")
BOT_USERNAME = os.getenv("BOT_USERNAME")
print("BOT USERNAME =", BOT_USERNAME)


# ====== CONFIG AIRTABLE ANNOTATIONS (table séparée) ======
ANNOT_API_KEY = os.getenv("ANNOT_API_KEY") or AIRTABLE_API_KEY
ANNOT_BASE_ID = os.getenv("ANNOT_BASE_ID") or BASE_ID
ANNOT_TABLE_NAME = os.getenv("ANNOT_TABLE_NAME")  # ex: "AnnotationsVIP"
# =========================================================


# =========================================================
# MEMOIRE RAM
# =========================================================
# user_id -> {
#   "topic_id": int,
#   "panel_message_id": int|None,
#   "note": str,
#   "admin_id": int|None,
#   "admin_name": str
# }
_user_topics = {}

# topic_id -> user_id
_topic_to_user = {}


# =========================================================
# HELPERS STRUCTURE
# =========================================================

def _ensure_user_entry(user_id: int) -> dict:
    """
    Garantit que _user_topics[user_id] est un dict complet (jamais un int).
    Corrige automatiquement les vieux formats.
    """
    existing = _user_topics.get(user_id)

    # Cas bug historique : _user_topics[user_id] = topic_id (int)
    if isinstance(existing, int):
        existing = {"topic_id": existing}

    if not isinstance(existing, dict):
        existing = {}

    entry = {
        "topic_id": existing.get("topic_id") if existing.get("topic_id") else None,
        "panel_message_id": existing.get("panel_message_id"),
        "note": existing.get("note", ""),
        "admin_id": existing.get("admin_id"),
        "admin_name": existing.get("admin_name", "Aucun"),
    }

    _user_topics[user_id] = entry
    return entry


# =========================================================
# JSON FALLBACK
# =========================================================

def save_vip_topics():
    """
    Sauvegarde locale (fallback). Sur Render ça peut sauter, donc Airtable reste la source de vérité.
    """
    try:
        data = {str(uid): info for uid, info in _user_topics.items()}
        with open(VIP_TOPICS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"[VIP_TOPICS] Sauvegarde JSON : {len(data)} topics enregistrés.")
    except Exception as e:
        print(f"[VIP_TOPICS] Erreur lors de la sauvegarde JSON : {e}")


def load_vip_topics_from_disk():
    """
    Recharge depuis vip_topics.json UNIQUEMENT ce qui est annotation/panel/admin,
    sans écraser les topic_id déjà chargés depuis Airtable.
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

            entry = _ensure_user_entry(user_id)

            # On ne remplace le topic_id QUE si Airtable n'a rien fourni
            if not entry.get("topic_id"):
                stored_topic = d.get("topic_id")
                if stored_topic:
                    try:
                        entry["topic_id"] = int(stored_topic)
                    except Exception:
                        pass

            # Merge annotation/panel
            if "panel_message_id" in d:
                entry["panel_message_id"] = d.get("panel_message_id")
            if "note" in d:
                entry["note"] = d.get("note", "")
            if "admin_id" in d:
                entry["admin_id"] = d.get("admin_id")
            if "admin_name" in d:
                entry["admin_name"] = d.get("admin_name", "Aucun")

            _user_topics[user_id] = entry

            if entry.get("topic_id"):
                _topic_to_user[int(entry["topic_id"])] = user_id

            merged += 1

        print(f"[VIP_TOPICS] Annotations restaurées depuis JSON pour {merged} VIP(s).")

    except FileNotFoundError:
        print("[VIP_TOPICS] Aucun fichier vip_topics.json à charger (normal si première exécution).")
    except Exception as e:
        print(f"[VIP_TOPICS] Erreur au chargement des annotations depuis JSON : {e}")


# =========================================================
# AIRTABLE (TOPIC ID) — SOURCE DE VERITE
# =========================================================

def _airtable_base_url() -> str | None:
    if not (AIRTABLE_API_KEY and BASE_ID and TABLE_NAME):
        return None
    return f"https://api.airtable.com/v0/{BASE_ID}/{TABLE_NAME.replace(' ', '%20')}"


def save_topic_id_to_airtable(user_id: int, topic_id: int) -> None:
    """
    Persiste Topic ID dans Airtable (pour TOUS les users, VIP ou non).
    """
    url_base = _airtable_base_url()
    if not url_base:
        print("[VIP_TOPICS] Airtable non configuré → skip save Topic ID.")
        return

    headers = {
        "Authorization": f"Bearer {AIRTABLE_API_KEY}",
        "Content-Type": "application/json"
    }

    fields = {"ID Telegram": str(user_id), "Topic ID": str(topic_id)}

    try:
        # On cherche une ligne existante pour ce user
        r = requests.get(
            url_base,
            headers=headers,
            params={"filterByFormula": f"{{ID Telegram}}='{user_id}'"}
        )
        r.raise_for_status()
        records = r.json().get("records", [])

        if records:
            rec_id = records[0]["id"]
            pr = requests.patch(f"{url_base}/{rec_id}", json={"fields": fields}, headers=headers)
            if pr.status_code not in (200, 201):
                print(f"[VIP_TOPICS] PATCH Topic ID failed: {pr.status_code} {pr.text}")
            else:
                print(f"[VIP_TOPICS] Topic ID {topic_id} sauvegardé (PATCH) pour user {user_id}")
        else:
            pr = requests.post(url_base, json={"fields": fields}, headers=headers)
            if pr.status_code not in (200, 201):
                print(f"[VIP_TOPICS] POST Topic ID failed: {pr.status_code} {pr.text}")
            else:
                print(f"[VIP_TOPICS] Topic ID {topic_id} sauvegardé (POST) pour user {user_id}")

    except Exception as e:
        print(f"[VIP_TOPICS] Erreur save_topic_id_to_airtable: {e}")


async def load_vip_topics_from_airtable():
    """
    Recharge tous les Topic ID existants depuis Airtable.
    C'est LA source de vérité pour éviter toute recréation après redéploiement.
    """
    url_base = _airtable_base_url()
    if not url_base:
        print("[VIP_TOPICS] Variables Airtable manquantes, impossible de charger les topics.")
        return

    headers = {"Authorization": f"Bearer {AIRTABLE_API_KEY}"}

    # ✅ robuste
    params = {"filterByFormula": "AND(NOT({Topic ID}=BLANK()), NOT({ID Telegram}=BLANK()))"}

    try:
        resp = requests.get(url_base, headers=headers, params=params)
        resp.raise_for_status()
        records = resp.json().get("records", [])
    except Exception as e:
        print(f"[VIP_TOPICS] Erreur import topics Airtable : {e}")
        return

    loaded = 0
    for rec in records:
        f = rec.get("fields", {})
        topic_id = f.get("Topic ID")
        telegram_id = f.get("ID Telegram")
        if not topic_id or not telegram_id:
            continue

        try:
            user_id = int(str(telegram_id).strip())
            topic_id_int = int(str(topic_id).strip())
        except Exception:
            continue

        entry = _ensure_user_entry(user_id)
        entry["topic_id"] = topic_id_int
        _user_topics[user_id] = entry
        _topic_to_user[topic_id_int] = user_id
        loaded += 1

    print(f"[VIP_TOPICS] {loaded} Topic IDs chargés depuis Airtable.")


# =========================================================
# ANNOTATIONS AIRTABLE (TABLE SEPAREE)
# =========================================================

def _annot_table_base_url() -> str | None:
    if not (ANNOT_API_KEY and ANNOT_BASE_ID and ANNOT_TABLE_NAME):
        return None
    return f"https://api.airtable.com/v0/{ANNOT_BASE_ID}/{ANNOT_TABLE_NAME.replace(' ', '%20')}"


def save_annotation_to_airtable(user_id: int, note: str, admin: str) -> bool:
    """
    Upsert une annotation dans la table annotations.
    Colonnes attendues : "ID Telegram", "Note", "Admin"
    """
    base_url = _annot_table_base_url()
    if not base_url:
        print("[ANNOTATION] Variables Airtable annotations manquantes, skip save.")
        return False

    headers = {
        "Authorization": f"Bearer {ANNOT_API_KEY}",
        "Content-Type": "application/json"
    }

    try:
        r = requests.get(base_url, headers=headers, params={"filterByFormula": f"{{ID Telegram}}='{user_id}'"})
        r.raise_for_status()
        records = r.json().get("records", [])
    except Exception as e:
        print(f"[ANNOTATION] Erreur recherche annotation Airtable pour user {user_id} : {e}")
        return False

    fields = {"ID Telegram": str(user_id), "Note": note or "", "Admin": admin or ""}

    try:
        if records:
            rec_id = records[0]["id"]
            pr = requests.patch(f"{base_url}/{rec_id}", json={"fields": fields}, headers=headers)
        else:
            pr = requests.post(base_url, json={"fields": fields}, headers=headers)

        if pr.status_code not in (200, 201):
            print(f"[ANNOTATION] Erreur save annotation user {user_id}: {pr.status_code} {pr.text}")
            return False

        return True

    except Exception as e:
        print(f"[ANNOTATION] Exception save_annotation_to_airtable user {user_id}: {e}")
        return False


def load_annotations_from_airtable():
    """
    Charge toutes les annotations Airtable et merge dans _user_topics (note/admin_name).
    """
    base_url = _annot_table_base_url()
    if not base_url:
        print("[ANNOTATION] Variables Airtable annotations manquantes, skip load.")
        return

    headers = {"Authorization": f"Bearer {ANNOT_API_KEY}"}

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
        if not telegram_id:
            continue

        try:
            user_id = int(str(telegram_id).strip())
        except Exception:
            continue

        entry = _ensure_user_entry(user_id)
        entry["note"] = f.get("Note", "") or ""
        entry["admin_name"] = f.get("Admin", "") or "Aucun"
        _user_topics[user_id] = entry
        loaded += 1

    print(f"[ANNOTATION] {loaded} annotations chargées depuis Airtable.")


# =========================================================
# TOPIC + PANEL CREATION
# =========================================================

async def create_topic_and_panel(user: types.User) -> int:
    user_id = user.id
    title = f"VIP {user.username or user.first_name or str(user_id)}"

    try:
        res = await bot.request("createForumTopic", {"chat_id": STAFF_GROUP_ID, "name": title})
    except Exception as e:
        print(f"[VIP_TOPICS] ERREUR createForumTopic pour {user_id} : {e}")
        return 0

    topic_id = res.get("message_thread_id")
    if not topic_id:
        print(f"[VIP_TOPICS] Pas de message_thread_id dans la réponse pour {user_id} : {res}")
        return 0

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

    entry = _ensure_user_entry(user_id)
    entry["topic_id"] = int(topic_id)
    entry["panel_message_id"] = panel_message_id
    _user_topics[user_id] = entry
    _topic_to_user[int(topic_id)] = user_id

    save_vip_topics()

    # ✅ PERSISTENCE AIRTABLE ICI (endroit correct)
    save_topic_id_to_airtable(user_id, int(topic_id))

    return int(topic_id)


async def ensure_topic_for_vip(user: types.User) -> int:
    """
    IMPORTANT :
    - Ici on NE dépend PAS de VIP pour conserver les topics.
    - Si Airtable a un Topic ID, on le réutilise.
    - Sinon, on crée et on sauvegarde dans Airtable.
    """
    user_id = user.id
    print(f"[VIP_TOPICS] ensure_topic_for_vip() appelé pour user_id={user_id}")

    entry = _ensure_user_entry(user_id)
    topic_id = entry.get("topic_id")

    # Si déjà connu → on renvoie et basta
    if topic_id:
        print(f"[VIP_TOPICS] Topic déjà connu pour {user_id} -> {topic_id}")
        return int(topic_id)

    # Sinon → création
    print(f"[VIP_TOPICS] {user_id} présent sans topic valide → création.")
    return await create_topic_and_panel(user)


# =========================================================
# UPDATE VIP INFO (notes/admin)
# =========================================================

def update_vip_info(user_id: int, note: str = None, admin_id: int = None, admin_name: str = None):
    entry = _ensure_user_entry(user_id)
    changed = False

    if note is not None:
        old = entry.get("note", "")
        entry["note"] = f"{old}\n{note}".strip() if old else (note or "")
        changed = True

    if admin_id is not None:
        entry["admin_id"] = admin_id
        changed = True

    if admin_name is not None:
        entry["admin_name"] = admin_name
        changed = True

    _user_topics[user_id] = entry
    save_vip_topics()

    if changed and ANNOT_TABLE_NAME:
        try:
            save_annotation_to_airtable(user_id, entry.get("note", ""), entry.get("admin_name", "Aucun"))
        except Exception as e:
            print(f"[ANNOTATION] Erreur sauvegarde Airtable : {e}")

    return entry


# =========================================================
# RESTORE PANELS
# =========================================================

async def restore_missing_panels():
    """
    Recrée un panneau si topic_id existe mais panel_message_id manquant.
    ⚠️ Ici on ne touche pas Airtable Topic ID (sinon bug scope).
    """
    restored = 0

    for user_id, info in list(_user_topics.items()):
        # sécurise format
        entry = _ensure_user_entry(int(user_id))

        topic_id = entry.get("topic_id")
        panel_message_id = entry.get("panel_message_id")

        if not topic_id:
            continue
        if panel_message_id:
            continue

        note = entry.get("note", "")
        admin_name = entry.get("admin_name", "Aucun")

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
                    "message_thread_id": int(topic_id),
                    "reply_markup": kb
                }
            )
            entry["panel_message_id"] = panel_res.get("message_id")
            _user_topics[int(user_id)] = entry
            restored += 1
            print(f"[VIP_TOPICS] Panneau restauré pour user_id={user_id} dans topic_id={topic_id}")

        except Exception as e:
            print(f"[VIP_TOPICS] Erreur restauration panneau pour user_id={user_id}: {e}")

    if restored > 0:
        save_vip_topics()

    print(f"[VIP_TOPICS] Panneaux restaurés pour {restored} VIP(s).")

# =========================================================
# HELPERS
# =========================================================

def is_vip(user_id: int) -> bool:
    return user_id in authorized_users


def get_user_id_by_topic_id(topic_id: int):
    return _topic_to_user.get(topic_id)


async def get_panel_message_id_by_user(user_id: int):
    entry = _ensure_user_entry(user_id)

    old_panel_id = entry.get("panel_message_id")
    topic_id = entry.get("topic_id")

    # 1️⃣ Si le panneau existe déjà → on le retourne
    if old_panel_id:
        return old_panel_id

    # 2️⃣ Si pas de topic → impossible
    if not topic_id:
        return None

    # 3️⃣ 🔥 Panel manquant → on le recrée automatiquement
    note = entry.get("note", "")
    admin_name = entry.get("admin_name", "Aucun")

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
        # Création du nouveau panel
        panel_res = await bot.request(
            "sendMessage",
            {
                "chat_id": STAFF_GROUP_ID,
                "text": panel_text,
                "message_thread_id": int(topic_id),
                "reply_markup": kb
            }
        )

        new_panel_id = panel_res.get("message_id")

        # 🔥 Désépingler explicitement l'ancien panel si existant
        if old_panel_id:
            try:
                await bot.request(
                    "unpinChatMessage",
                    {
                        "chat_id": STAFF_GROUP_ID,
                        "message_id": old_panel_id
                    }
                )
            except Exception as e:
                print(f"[VIP_TOPICS] Impossible de désépingler l'ancien panel pour user_id={user_id}: {e}")

        # 🔥 Épingler le nouveau panel
        try:
            await bot.request(
                "pinChatMessage",
                {
                    "chat_id": STAFF_GROUP_ID,
                    "message_id": new_panel_id,
                    "disable_notification": True
                }
            )
        except Exception as e:
            print(f"[VIP_TOPICS] Impossible d'épingler le panel pour user_id={user_id}: {e}")

        # Sauvegarde
        entry["panel_message_id"] = new_panel_id
        _user_topics[user_id] = entry
        save_vip_topics()

        print(f"[VIP_TOPICS] Panel recréé dynamiquement pour user_id={user_id}")
        return new_panel_id

    except Exception as e:
        print(f"[VIP_TOPICS] Erreur recréation panel user_id={user_id}: {e}")
        return None
