# ban_manager.py
import json
import os

BAN_FILE = "bannis.json"

# === Chargement de la ban_list structurée par admin_id ===
def load_ban_list():
    if os.path.exists(BAN_FILE):
        try:
            with open(BAN_FILE, "r") as f:
                data = json.load(f)
                return {int(k): set(v) for k, v in data.items()}
        except Exception as e:
            print(f"Erreur chargement bannis.json : {e}")
    return {}

def save_ban_list():
    with open(BAN_FILE, "w") as f:
        json.dump({str(k): list(v) for k, v in ban_list.items()}, f)

# === Initialisation globale ===
ban_list = load_ban_list()

# === Fonctions de gestion ===
def is_banned(user_id, admin_id):
    return user_id in ban_list.get(admin_id, set())

def add_ban(user_id, admin_id):
    ban_list.setdefault(admin_id, set()).add(user_id)
    save_ban_list()

def remove_ban(user_id, admin_id):
    if user_id in ban_list.get(admin_id, set()):
        ban_list[admin_id].remove(user_id)
        save_ban_list()

# === Exports autorisés ===
__all__ = ["is_banned", "add_ban", "remove_ban", "ban_list"]
