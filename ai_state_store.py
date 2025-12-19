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

def _raise(r: requests.Response, label: str):
    try:
        r.raise_for_status()
    except Exception:
        print(f"[AIRTABLE ERROR] {label} {r.status_code} {r.text}")
        raise

def _get_first_record(table: str, formula: str) -> Optional[Dict[str, Any]]:
    _ensure_cfg()
    url = f"{BASE_URL}/{_table_url(table)}"
    params = {"filterByFormula": formula, "maxRecords": 1}
    r = requests.get(url, headers=HEADERS, params=params, timeout=20)
    _raise(r, f"GET {table}")
    recs = r.json().get("records", [])
    return recs[0] if recs else None

def _get_records(table: str, formula: str, max_records: int = 50) -> List[Dict[str, Any]]:
    _ensure_cfg()
    url = f"{BASE_URL}/{_table_url(table)}"
    params = {"filterByFormula": formula, "pageSize": min(max_records, 100)}
    r = requests.get(url, headers=HEADERS, params=params, timeout=20)
    _raise(r, f"GET {table}")
    return r.json().get("records", [])[:max_records]

def _patch_record(table: str, record_id: str, fields: Dict[str, Any]) -> None:
    _ensure_cfg()
    url = f"{BASE_URL}/{_table_url(table)}/{record_id}"
    payload = {"fields": fields}
    r = requests.patch(url, headers=HEADERS, json=payload, timeout=20)
    _raise(r, f"PATCH {table}")
    print("[AIRTABLE PATCH]", {"table": table, "record_id": record_id, "fields": fields})

def _create_record(table: str, fields: Dict[str, Any]) -> Dict[str, Any]:
    _ensure_cfg()
    url = f"{BASE_URL}/{_table_url(table)}"
    payload = {"fields": fields}
    r = requests.post(url, headers=HEADERS, json=payload, timeout=20)
    _raise(r, f"CREATE {table}")
    rec = r.json()
    print("[AIRTABLE CREATE]", fields)
    return rec

# ================== AI STATE ==================

def get_state(user_id: int) -> Optional[Dict[str, Any]]:
    """
    Retourne {"id": airtable_record_id, "fields": {...}} ou None
    Telegram ID est un champ texte -> comparaison en string
    """
    uid = str(int(user_id))
    rec = _get_first_record(AI_STATE_TABLE, f"{{Telegram ID}}='{uid}'")
    if not rec:
        return None
    return {"id": rec["id"], "fields": rec.get("fields", {})}

def upsert_state(user_id: int, updates: Dict[str, Any]) -> None:
    """
    Crée la ligne si absente puis patch.
    Important: Telegram ID est du texte => on écrit une string.
    """
    uid = str(int(user_id))
    st = get_state(user_id)

    if st is None:
        # ✅ CREATE avec Telegram ID en string
        base_fields = {"Telegram ID": uid}
        base_fields.update(updates)

        try:
            _create_record(AI_STATE_TABLE, base_fields)
            return
        except Exception:
            # 🔥 fallback (au cas où Airtable refuse à cause d'une config chelou)
            # On crée sans Telegram ID puis on essaye de patch Telegram ID ensuite
            print("[AIRTABLE WARN] CREATE with Telegram ID failed -> fallback create without it")
            rec = _create_record(AI_STATE_TABLE, updates)
            rec_id = rec.get("id")
            if rec_id:
                try:
                    _patch_record(AI_STATE_TABLE, rec_id, {"Telegram ID": uid})
                except Exception:
                    print("[AIRTABLE WARN] fallback patch Telegram ID failed")
            return

    _patch_record(AI_STATE_TABLE, st["id"], updates)

# ================== SCRIPTS ==================

def get_script_json(script_id: str) -> Optional[Dict[str, Any]]:
    rec = _get_first_record(SCRIPT_TABLE, f"{{Script ID}}='{script_id}'")
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
    - Price Code
    """
    if not list_id:
        return []

    parts = [f"{{List ID}}='{list_id}'", "{Active}=TRUE()"]
    if stage:
        parts.append(f"{{Stage}}='{stage}'")
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
