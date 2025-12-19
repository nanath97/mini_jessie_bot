# ai_state_store.py
import os
import json
import requests
from typing import Any, Dict, Optional, List

AIRTABLE_API_KEY = os.getenv("AIRTABLE_API_KEY", "")
BASE_ID = os.getenv("BASE_ID", "")

AI_STATE_TABLE = os.getenv("AIRTABLE_TABLE_AI_STATE", "AI_STATE")
SCRIPT_TABLE = os.getenv("AIRTABLE_TABLE_SCRIPTS", "ScriptOFM")

# ✅ IMPORTANT: chez toi c'est inversé par rapport aux noms "logiques"
# MEDIA_LIST = table des médias (Media ID, Telegram File ID, etc.)
# MEDIA_LIBRARY = table des listes (List ID, Name, Active...)
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


def _airtable_escape_str(s: str) -> str:
    # Airtable filterByFormula uses single quotes; escape them by doubling.
    return s.replace("'", "''")


def _get_first_record(table: str, formula: str) -> Optional[Dict[str, Any]]:
    _ensure_cfg()
    url = f"{BASE_URL}/{_table_url(table)}"
    params = {"filterByFormula": formula, "maxRecords": 1}
    r = requests.get(url, headers=HEADERS, params=params, timeout=20)
    if not r.ok:
        print("[AIRTABLE GET ERROR]", r.status_code, r.text)
    r.raise_for_status()
    recs = r.json().get("records", [])
    return recs[0] if recs else None


def _get_records(table: str, formula: str, max_records: int = 50) -> List[Dict[str, Any]]:
    _ensure_cfg()
    url = f"{BASE_URL}/{_table_url(table)}"
    params = {"filterByFormula": formula, "pageSize": min(max_records, 100)}
    r = requests.get(url, headers=HEADERS, params=params, timeout=20)
    if not r.ok:
        print("[AIRTABLE GET ERROR]", r.status_code, r.text)
    r.raise_for_status()
    return r.json().get("records", [])[:max_records]


def _patch_record(table: str, record_id: str, fields: Dict[str, Any]) -> None:
    _ensure_cfg()
    url = f"{BASE_URL}/{_table_url(table)}/{record_id}"
    payload = {"fields": fields}

    print("[AIRTABLE PATCH] table=", table, "record_id=", record_id, "fields=", fields)

    r = requests.patch(url, headers=HEADERS, data=json.dumps(payload), timeout=20)
    if not r.ok:
        print("[AIRTABLE PATCH ERROR]", r.status_code, r.text)
    r.raise_for_status()


def _create_record(table: str, fields: Dict[str, Any]) -> None:
    _ensure_cfg()
    url = f"{BASE_URL}/{_table_url(table)}"
    payload = {"fields": fields}

    print("[AIRTABLE CREATE] table=", table, "fields=", fields)

    r = requests.post(url, headers=HEADERS, data=json.dumps(payload), timeout=20)
    if not r.ok:
        print("[AIRTABLE CREATE ERROR]", r.status_code, r.text)
    r.raise_for_status()


# ================== AI STATE ==================

def get_state(user_id: int) -> Optional[Dict[str, Any]]:
    """
    Retourne {"id": airtable_record_id, "fields": {...}} ou None

    ✅ On cherche Telegram ID en texte (robuste si colonne = Single line text)
    """
    uid = str(user_id)
    uid_esc = _airtable_escape_str(uid)

    # Priorité: match texte
    rec = _get_first_record(AI_STATE_TABLE, f"{{Telegram ID}}='{uid_esc}'")
    if rec:
        return {"id": rec["id"], "fields": rec.get("fields", {})}

    # Fallback (si jamais colonne est bien Number chez certains clients)
    rec = _get_first_record(AI_STATE_TABLE, f"{{Telegram ID}}={int(user_id)}")
    if not rec:
        return None

    return {"id": rec["id"], "fields": rec.get("fields", {})}


def upsert_state(user_id: int, updates: Dict[str, Any]) -> None:
    """
    Crée la ligne si absente puis patch.

    ✅ On écrit Telegram ID en string pour éviter INVALID_VALUE_FOR_COLUMN
    """
    st = get_state(user_id)
    if st is None:
        base_fields = {"Telegram ID": str(user_id)}
        base_fields.update(updates)
        _create_record(AI_STATE_TABLE, base_fields)
        return

    _patch_record(AI_STATE_TABLE, st["id"], updates)


# ================== SCRIPTS ==================

def get_script_json(script_id: str) -> Optional[Dict[str, Any]]:
    rec = _get_first_record(SCRIPT_TABLE, f"{{Script ID}}='{_airtable_escape_str(script_id)}'")
    if not rec:
        return None
    fields = rec.get("fields", {})
    raw = fields.get("Script JSON")
    if not raw:
        return None
    if isinstance(raw, dict):
        return raw
    try:
        return json.loads(raw)
    except Exception:
        return None


# ================== MEDIA ==================

def get_media_candidates(list_id: str, stage: Optional[str] = None, limit: int = 25) -> List[Dict[str, Any]]:
    """
    Lit dans MEDIA_ITEMS_TABLE (= 'MEDIA_LIST' chez toi)
    Colonnes attendues :
    - List ID
    - Active (checkbox)
    - Telegram File ID
    - Media Type
    - Stage
    - Media ID
    - Desc Short
    - Price Code (optionnel)
    """
    if not list_id:
        return []

    list_id_esc = _airtable_escape_str(list_id)
    parts = [f"{{List ID}}='{list_id_esc}'", "{Active}=TRUE()"]
    if stage:
        parts.append(f"{{Stage}}='{_airtable_escape_str(stage)}'")
    formula = "AND(" + ",".join(parts) + ")"

    recs = _get_records(MEDIA_ITEMS_TABLE, formula, max_records=limit)
    out = []
    for r in recs:
        f = r.get("fields", {})
        out.append({
            "media_id": f.get("Media ID"),
            "list_id": f.get("List ID"),
            "file_id": f.get("Telegram File ID"),
            "media_type": f.get("Media Type"),
            "stage": f.get("Stage"),
            "desc_short": f.get("Desc Short"),
            "price_code": f.get("Price Code"),
        })
    return out
