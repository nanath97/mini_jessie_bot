# staff_system.py

import json
import os
from aiogram import types
from core import dp, bot, authorized_users

# Configuration : ID du groupe staff (type forum)
STAFF_FEATURE_ENABLED = True
STAFF_GROUP_ID = -1003418175247  # ← remplace par l’ID de ton groupe forum staff

# Fichier pour stocker les correspondances utilisateur ↔ topic
TOPIC_MAP_FILE = "staff_topics.json"
_map = {}

# Charger les topics existants depuis fichier
if os.path.exists(TOPIC_MAP_FILE):
    with open(TOPIC_MAP_FILE, "r") as f:
        _map = json.load(f)


def save_topic_map():
    with open(TOPIC_MAP_FILE, "w") as f:
        json.dump(_map, f)


# Créer un topic pour le client s’il n’existe pas encore
async def ensure_topic_for(bot, user_id, username="", email="", total_spent=0.0):
    global _map
    if str(user_id) in _map:
        return  # déjà créé

    # Nom du topic
    thread_name = f"{username or user_id} – VIP"
    if total_spent > 0:
        thread_name += f" ({int(total_spent)}€)"

    try:
        forum_topic = await bot.create_forum_topic(
            chat_id=STAFF_GROUP_ID,
            name=thread_name
        )
        _map[str(user_id)] = {
            "thread_id": forum_topic.message_thread_id,
            "owner_id": user_id,
            "username": username,
            "email": email,
            "total_spent": total_spent
        }
        save_topic_map()
    except Exception as e:
        print(f"[staff_system] Erreur création topic pour {user_id} : {e}")


# Copier le message privé du client vers son topic staff
async def mirror_client_to_staff(bot, message: types.Message):
    if not STAFF_FEATURE_ENABLED or message.chat.type != "private":
        return

    user_id = message.from_user.id
    if str(user_id) not in _map:
        await ensure_topic_for(bot, user_id, message.from_user.username)
    thread_id = _map[str(user_id)]["thread_id"]

    try:
        await bot.copy_message(
            chat_id=STAFF_GROUP_ID,
            from_chat_id=message.chat.id,
            message_id=message.message_id,
            message_thread_id=thread_id
        )
    except Exception as e:
        print(f"[staff_system] Erreur copie message VIP vers topic : {e}")


# Réponse du staff → renvoyer vers le client
@dp.message_handler(
    lambda m: m.chat.id == STAFF_GROUP_ID and getattr(m, "message_thread_id", None) is not None,
    content_types=types.ContentTypes.ANY
)
async def _outbound(m: types.Message):
    try:
        thread_id = m.message_thread_id
        for uid, val in _map.items():
            if val["thread_id"] == thread_id:
                user_id = int(uid)
                await m.send_copy(chat_id=user_id)
                break
    except Exception as e:
        print(f"[staff_system] Erreur retour vers client : {e}")
