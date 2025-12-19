import os
import json
import requests
from typing import Any, Dict, Optional

# ================== CONFIG ==================

AIRTABLE_API_KEY = os.getenv("AIRTABLE_API_KEY", "")
BASE_ID = os.getenv("BASE_ID", "")

AI_STATE_TABLE = os.getenv("AIRTABLE_TABLE_AI_STATE", "AI_STATE")
SCRIPT_TABLE = os.getenv("AIRTABLE_TABLE_SCRIPTS", "ScriptOFM")

BASE_URL = f"https://api.airtable.com/v0/{BASE_ID}"

HEADERS = {
    "Authorization": f"Bearer {AIRTABLE_API_KEY}",
    "Content-Type": "application/json",
}

# ================== HELPERS ==================

def _ensure_cfg():
    if not AIRTABLE_API_KEY or not BASE_ID:
        raise RuntimeError("Airtable config missing: set AIRTABLE_API_KEY and BASE_ID")

def _table_url(table_name: str) -> str:
    return table_name.replace(" ", "%20")

def _get_first_record(table: str, formula: str) -> Optional[Dict[str, Any]]:
    _ensure_cfg()
    url = f"{BASE_URL}/{_table_url(table)}"
    params = {
        "filterByFormula": formula,
        "maxRecords": 1
    }
    r = requests.get(url, headers=HEADERS, params=params, timeout=20)
    r.raise_for_status()
    records = r.json().get("records", [])
    return records[0] if records else None

# ================== AI STATE ==================

def get_state(telegram_id: int) -> Optional[Dict[str, Any]]:
    """
    Récupère l'état AI_STATE pour un Telegram ID
    Telegram ID est un champ TEXTE => comparaison avec quotes
    """
    return _get_first_record(
        AI_STATE_TABLE,
        f"{{Telegram ID}}='{telegram_id}'"
    )

def upsert_state(telegram_id: int, fields: Dict[str, Any]) -> Dict[str, Any]:
    """
    Insert ou update l'état AI_STATE pour un Telegram ID
    """
    _ensure_cfg()
    url = f"{BASE_URL}/{_table_url(AI_STATE_TABLE)}"
    existing = get_state(telegram_id)

    # ⚠️ IMPORTANT :
    # - Telegram ID = string
    # - Les champs JSON doivent être stringifiés AVANT d'arriver ici
    payload = {
        "fields": {
            "Telegram ID": str(telegram_id),
            **fields
        }
    }

    if existing:
        record_id = existing["id"]
        r = requests.patch(
            f"{url}/{record_id}",
            headers=HEADERS,
            json=payload,
            timeout=20
        )
    else:
        r = requests.post(
            url,
            headers=HEADERS,
            json=payload,
            timeout=20
        )

    # 🔥 DEBUG CRITIQUE
    if r.status_code == 422:
        print("❌ Airtable 422 — payload rejected")
        print("Payload envoyé :")
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        print("Réponse Airtable :")
        print(r.text)

    r.raise_for_status()
    return r.json()

# ================== SCRIPTS ==================

def get_script_record(script_id: str) -> Optional[Dict[str, Any]]:
    """
    Récupère un script depuis ScriptOFM via Script ID
    """
    if not script_id:
        return None

    rec = _get_first_record(
        SCRIPT_TABLE,
        f"{{Script ID}}='{script_id}'"
    )
    return rec["fields"] if rec else None
