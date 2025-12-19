# ai_state_store.py
import os
import json
import requests
from typing import Any, Dict, Optional, List

AIRTABLE_API_KEY = os.getenv("AIRTABLE_API_KEY", "")
BASE_ID = os.getenv("BASE_ID", "")

AI_STATE_TABLE = os.getenv("AIRTABLE_TABLE_AI_STATE", "AI_STATE")
SCRIPT_TABLE = os.getenv("AIRTABLE_TABLE_SCRIPTS", "ScriptOFM")

MEDIA_ITEMS_TABLE = os.getenv("AIRTABLE_TABLE_MEDIA_ITEMS", "MEDIA_LIST")
MEDIA_LISTS_TABLE = os.getenv("AIRTABLE_TABLE_MEDIA_LISTS", "MEDIA_LIBRARY")

BASE_URL = f"https://api.airtable.com/v0/{BASE_ID}"

HEADERS = {
    "Authorization": f"Bearer {AIRTABLE_API_KEY}",
    "Content-Type": "application/json",
}

def _ensure_cfg():
    if not AIRTABLE_API_KEY or not BASE_ID:
        raise RuntimeError("AIRTABLE_API_KEY ou BASE_ID manquant")

def _table_url(name: str) -> str:
    return name.replace(" ", "%20")

def _raise(r, label=""):
    try:
        r.raise_for_status()
    except Exception:
        print(f"[AIRTABLE ERROR] {label} {r.status_code} {r.text}")
        raise

def _get_first_record(table: str, formula: str):
    _ensure_cfg()
    r = requests.get(
        f"{BASE_URL}/{_table_url(table)}",
        headers=HEADERS,
        params={"filterByFormula": formula, "maxRecords": 1},
        timeout=20
    )
    _raise(r, f"GET {table}")
    recs = r.json().get("records", [])
    return recs[0] if recs else None

def _patch_record(table: str, record_id: str, fields: Dict[str, Any]):
    _ensure_cfg()
    r = requests.patch(
        f"{BASE_URL}/{_table_url(table)}/{record_id}",
        headers=HEADERS,
        json={"fields": fields},
        timeout=20
    )
    _raise(r, f"PATCH {table}")
    print("[AIRTABLE PATCH]", record_id, fields)

def _create_record(table: str, fields: Dict[str, Any]):
    _ensure_cfg()
    r = requests.post(
        f"{BASE_URL}/{_table_url(table)}",
        headers=HEADERS,
        json={"fields": fields},
        timeout=20
    )
    _raise(r, f"CREATE {table}")
    print("[AIRTABLE CREATE]", fields)

# ================== AI STATE ==================

def get_state(user_id: int):
    # ⚠️ on NE TOUCHE PAS au champ Telegram ID ici
    formula = f"{{Telegram ID}}='{user_id}'"
    rec = _get_first_record(AI_STATE_TABLE, formula)
    if not rec:
        return None
    return {"id": rec["id"], "fields": rec.get("fields", {})}

def upsert_state(user_id: int, updates: Dict[str, Any]):
    st = get_state(user_id)

    if st is None:
        # 🔥 ON NE CRÉE PAS Telegram ID
        _create_record(AI_STATE_TABLE, updates)
        return

    _patch_record(AI_STATE_TABLE, st["id"], updates)

# ================== SCRIPTS ==================

def get_script_json(script_id: str):
    rec = _get_first_record(SCRIPT_TABLE, f"{{Script ID}}='{script_id}'")
    if not rec:
        return None
    raw = rec.get("fields", {}).get("Script JSON")
    if isinstance(raw, dict):
        return raw
    try:
        return json.loads(raw)
    except Exception:
        return None

# ================== MEDIA ==================

def get_media_candidates(list_id: str, stage: Optional[str] = None, limit: int = 25):
    if not list_id:
        return []

    parts = [f"{{List ID}}='{list_id}'", "{Active}=TRUE()"]
    if stage:
        parts.append(f"{{Stage}}='{stage}'")

    formula = "AND(" + ",".join(parts) + ")"
    r = requests.get(
        f"{BASE_URL}/{_table_url(MEDIA_ITEMS_TABLE)}",
        headers=HEADERS,
        params={"filterByFormula": formula},
        timeout=20
    )
    _raise(r, "GET MEDIA")

    out = []
    for rec in r.json().get("records", []):
        f = rec.get("fields", {})
        out.append({
            "media_id": f.get("Media ID"),
            "file_id": f.get("Telegram File ID"),
            "media_type": f.get("Media Type"),
            "stage": f.get("Stage"),
            "desc_short": f.get("Desc Short"),
            "price_code": f.get("Price Code"),
        })
    return out
