import os
import requests
from typing import Any, Dict, Optional

AIRTABLE_API_KEY = os.getenv("AIRTABLE_API_KEY", "")
BASE_ID = os.getenv("BASE_ID", "")

# Tables
AI_STATE_TABLE = os.getenv("AIRTABLE_TABLE_AI_STATE", "AI_STATE")
SCRIPT_TABLE = os.getenv("AIRTABLE_TABLE_SCRIPTS", "ScriptOFM")  # visible in your base

def _table_url(table_name: str) -> str:
    return table_name.replace(" ", "%20")

BASE_URL = f"https://api.airtable.com/v0/{BASE_ID}"

HEADERS = {
    "Authorization": f"Bearer {AIRTABLE_API_KEY}",
    "Content-Type": "application/json",
}

def _ensure_cfg():
    if not AIRTABLE_API_KEY or not BASE_ID:
        raise RuntimeError("Airtable config missing: set AIRTABLE_API_KEY and BASE_ID env vars.")

def _get_first_record(table: str, formula: str) -> Optional[Dict[str, Any]]:
    _ensure_cfg()
    url = f"{BASE_URL}/{_table_url(table)}"
    params = {"filterByFormula": formula, "maxRecords": 1}
    r = requests.get(url, headers=HEADERS, params=params, timeout=20)
    r.raise_for_status()
    data = r.json()
    recs = data.get("records", [])
    return recs[0] if recs else None

def get_state(telegram_id: int) -> Optional[Dict[str, Any]]:
    """Return the Airtable AI_STATE record for this Telegram ID, or None."""
    rec = _get_first_record(AI_STATE_TABLE, f"{{Telegram ID}}='{telegram_id}'")
    return rec

def upsert_state(telegram_id: int, fields: Dict[str, Any]) -> Dict[str, Any]:
    """Upsert fields into AI_STATE for this Telegram ID."""
    _ensure_cfg()
    url = f"{BASE_URL}/{_table_url(AI_STATE_TABLE)}"
    existing = get_state(telegram_id)

    payload = {"fields": {"Telegram ID": str(telegram_id), **fields}}

    if existing:
        rid = existing["id"]
        r = requests.patch(f"{url}/{rid}", headers=HEADERS, json=payload, timeout=20)
    else:
        r = requests.post(url, headers=HEADERS, json=payload, timeout=20)

    r.raise_for_status()
    return r.json()

def get_script_record(script_id: str) -> Optional[Dict[str, Any]]:
    """Fetch a ScriptOFM (or other script table) record by Script ID."""
    if not script_id:
        return None
    return _get_first_record(SCRIPT_TABLE, f"{{Script ID}}='{script_id}'")

def get_script_from_airtable(script_id: str):
    url = f"{AIRTABLE_BASE_URL}/ScriptOFM"
    params = {
        "filterByFormula": f"{{Script ID}}='{script_id}'"
    }
    r = requests.get(url, headers=HEADERS, params=params)
    r.raise_for_status()
    records = r.json().get("records", [])
    return records[0]["fields"] if records else None


