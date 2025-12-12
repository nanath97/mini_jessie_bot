import os
import requests

AIRTABLE_API_KEY = os.getenv("AIRTABLE_API_KEY")
BASE_ID = os.getenv("BASE_ID")

AI_STATE_TABLE = os.getenv("AIRTABLE_TABLE_AI_STATE", "AI_STATE")
AI_STATE_TABLE_URL = AI_STATE_TABLE.replace(" ", "%20")

BASE_URL = f"https://api.airtable.com/v0/{BASE_ID}/{AI_STATE_TABLE_URL}"

HEADERS = {
    "Authorization": f"Bearer {AIRTABLE_API_KEY}",
    "Content-Type": "application/json"
}

def get_state(telegram_id: int):
    formula = f"{{Telegram ID}}='{telegram_id}'"
    r = requests.get(BASE_URL, headers=HEADERS, params={
        "filterByFormula": formula,
        "maxRecords": 1
    })
    r.raise_for_status()
    records = r.json().get("records", [])
    return records[0] if records else None


def upsert_state(telegram_id: int, fields: dict):
    record = get_state(telegram_id)
    payload = {
        "fields": {
            "Telegram ID": str(telegram_id),
            **fields
        }
    }

    if record:
        r = requests.patch(f"{BASE_URL}/{record['id']}", headers=HEADERS, json=payload)
    else:
        r = requests.post(BASE_URL, headers=HEADERS, json=payload)

    r.raise_for_status()
    return r.json()
