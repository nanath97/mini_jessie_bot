# ban_manager.py
import json
import os

BAN_FILE = "bannis.json"

def load_ban_list():
    if not os.path.exists(BAN_FILE):
        return set()
    try:
        with open(BAN_FILE, "r") as f:
            return set(json.load(f))
    except Exception as e:
        print(f"Erreur chargement bannis.json : {e}")
        return set()

def save_ban_list(ban_set):
    with open(BAN_FILE, "w") as f:
        json.dump(list(ban_set), f)

def is_banned(user_id):
    return user_id in load_ban_list()

def add_ban(user_id):
    ban_set = load_ban_list()
    ban_set.add(user_id)
    save_ban_list(ban_set)

def remove_ban(user_id):
    ban_set = load_ban_list()
    if user_id in ban_set:
        ban_set.remove(user_id)
        save_ban_list(ban_set)
