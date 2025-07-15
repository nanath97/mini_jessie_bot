import os
import requests

BASE_ID = os.getenv("BASE_ID")
AIRTABLE_API_KEY = os.getenv("AIRTABLE_API_KEY")
TABLE_NAME = os.getenv("TABLE_NAME")  # on va l'utiliser même si c'est générique

def get_all_vip_ids():
    url = f"https://api.airtable.com/v0/{BASE_ID}/{TABLE_NAME}"
    headers = {
        "Authorization": f"Bearer {AIRTABLE_API_KEY}"
    }

    vip_ids = []

    offset = None
    while True:
        params = {"offset": offset} if offset else {}
        try:
            response = requests.get(url, headers=headers, params=params)
            response.raise_for_status()
            data = response.json()
        except Exception as e:
            print(f"❌ Erreur récupération Airtable : {e}")
            break

        for record in data.get("records", []):
            fields = record.get("fields", {})
            telegram_id = fields.get("ID Telegram")
            if telegram_id:
                try:
                    vip_ids.append(int(telegram_id))
                except:
                    print(f"⚠️ ID Telegram invalide : {telegram_id}")

        offset = data.get("offset")
        if not offset:
            break

    return vip_ids
