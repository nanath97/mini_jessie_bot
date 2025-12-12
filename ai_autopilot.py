import os
import json
import random
import re
import datetime
from ai_state_store import get_state, upsert_state
from aiogram import types

# ---------------- CONFIG ----------------
STAFF_GROUP_ID = int(os.getenv("STAFF_GROUP_ID", "0"))
COOLDOWN_SECONDS = 8

# Si ton fichier est à la racine, laisse "script_fr_v1.json"
# Si tu le mets dans un dossier: "scripts/script_fr_v1.json"
SCRIPT_PATH = os.getenv("AI_SCRIPT_PATH", "script_fr_v1.json")

BOT_PROFILE = {
    "name": "Jessie",
    "city": "Paris",
    "age": "23",
    "job": "créatrice",
    "single": "célibataire"
}

# ---------------- Utils ----------------
def _utcnow() -> datetime.datetime:
    return datetime.datetime.utcnow()

def _parse_airtable_dt(dt_str: str):
    if not dt_str:
        return None
    try:
        return datetime.datetime.fromisoformat(dt_str.replace("Z", ""))
    except Exception:
        return None

def _safe_json_loads(s: str, default):
    try:
        return json.loads(s) if s else default
    except Exception:
        return default

def _render(template: str, profile: dict) -> str:
    out = template
    for k, v in profile.items():
        if k.startswith("__"):
            continue
        out = out.replace("{" + k + "}", str(v))
    return out

def _extract_age(text: str):
    if not text:
        return None
    m = re.search(r"\b(\d{1,2})\b", text)
    if not m:
        return None
    age = int(m.group(1))
    if 0 < age < 100:
        return age
    return None

def _normalize_yes_no(text: str):
    if not text:
        return None
    t = text.strip().lower()
    yes = {"oui", "ouais", "yep", "yeah", "si", "claro", "ok", "daccord", "d'accord", "bien sur", "bien sûr"}
    no = {"non", "nope", "nan", "pas", "pas du tout"}
    if any(x == t or x in t for x in yes):
        return "oui"
    if any(x == t or x in t for x in no):
        return "non"
    return None

def is_et_toi(text: str) -> bool:
    t = (text or "").strip().lower()
    return ("et toi" in t) or ("toi ?" in t) or ("toi aussi" in t)

def _load_script():
    with open(SCRIPT_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

# ---------------- Load script at startup ----------------
try:
    SCRIPT = _load_script()
except Exception as e:
    print(f"❌ [AI] Impossible de charger le script {SCRIPT_PATH}: {e}")
    SCRIPT = None


async def maybe_run_autopilot(message: types.Message, topic_id: int, bot):
    # 1) TEXT ONLY (safe MVP)
    if message.content_type != types.ContentType.TEXT:
        return

    # Script must be loaded
    if not SCRIPT or "steps" not in SCRIPT:
        return

    user_id = message.from_user.id
    now = _utcnow()

    state = get_state(user_id)

    # 2) Create state if not exists
    if not state:
        upsert_state(user_id, {
            "Topic ID": str(topic_id),
            "Script ID": SCRIPT.get("script_id", "script_fr_v1"),
            "Step Index": 0,
            "Profile JSON": "{}",
            "Heat": 0,
            "Pending Fillers JSON": "[]",
            "Autopilot": "OFF",
            "Cooldown Until": None
        })
        return

    fields = state.get("fields", {})

    # 3) Autopilot OFF → silence
    if fields.get("Autopilot") != "ON":
        return

    # 4) Cooldown
    cooldown_str = fields.get("Cooldown Until")
    cd_time = _parse_airtable_dt(cooldown_str) if cooldown_str else None
    if cd_time and now < cd_time:
        return

    # 5) Load profile + step
    profile = _safe_json_loads(fields.get("Profile JSON"), {})
    if not isinstance(profile, dict):
        profile = {}

    steps = SCRIPT["steps"]
    step_index = int(fields.get("Step Index") or 0)

    if step_index < 0:
        step_index = 0
    if step_index >= len(steps):
        step_index = len(steps) - 1

    user_text = (message.text or "").strip()
    asked = is_et_toi(user_text)

    # 6) Fill slot if waiting
    waiting_slot = profile.get("__waiting_slot")
    if waiting_slot:
        if waiting_slot == "age":
            age = _extract_age(user_text)
            if age is not None:
                profile["age"] = age
                if age < 18:
                    await bot.send_message(user_id, "Désolé, je ne peux pas continuer.")
                    upsert_state(user_id, {
                        "Autopilot": "OFF",
                        "Profile JSON": json.dumps(profile, ensure_ascii=False),
                        "Cooldown Until": (now + datetime.timedelta(seconds=COOLDOWN_SECONDS)).isoformat()
                    })
                    return
            else:
                # pas d'âge détecté → on ne remplit pas (MVP)
                pass

        elif waiting_slot == "celibataire":
            yn = _normalize_yes_no(user_text)
            profile["celibataire"] = yn if yn else user_text

        else:
            if user_text:
                profile[waiting_slot] = user_text

        # stop waiting
        profile["__waiting_slot"] = None

        # advance step
        step_index = min(step_index + 1, len(steps) - 1)

        # persist now
        upsert_state(user_id, {
            "Profile JSON": json.dumps(profile, ensure_ascii=False),
            "Step Index": step_index
        })

    # 7) Build step message
    current_step = steps[step_index]
    slot = current_step.get("slot")
    messages = current_step.get("messages") or []

    msg_out = random.choice(messages) if messages else "😌"
    msg_out = _render(msg_out, profile)

    # 8) PRIORITÉ "et toi ?" (version simple)
    # Réponse courte + script ensuite
    final_out = msg_out
    if asked:
    # version fluide (pas en 2 lignes)
        final_out = f"Moi c’est {BOT_PROFILE['name']} 😌 {msg_out}"


    # ✅ send to client
    await bot.send_message(user_id, final_out)

    # ✅ log in staff topic (compatible)
    if STAFF_GROUP_ID and topic_id:
        try:
            await bot.request("sendMessage", {
                "chat_id": STAFF_GROUP_ID,
                "message_thread_id": topic_id,
                "text": f"[AUTO][STEP {step_index}] → {final_out}"
            })
        except Exception as e:
            print(f"❌ [AI] log staff failed: {e}")

    # 9) Update waiting slot / step index
    if slot:
        profile["__waiting_slot"] = slot
        upsert_state(user_id, {
            "Profile JSON": json.dumps(profile, ensure_ascii=False),
            "Step Index": step_index
        })
    else:
        upsert_state(user_id, {"Step Index": step_index + 1})

    # 10) Cooldown
    upsert_state(user_id, {
        "Cooldown Until": (now + datetime.timedelta(seconds=COOLDOWN_SECONDS)).isoformat()
    })
