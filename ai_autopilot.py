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

# Tu as choisi de le garder à la racine -> OK
SCRIPT_PATH = os.getenv("AI_SCRIPT_PATH", "script_fr_v1.json")

BOT_PROFILE = {
    "name": "Jessie",
    "city": "Haute-Savoie, dans les montagnes haha",
    "age": "23",
    "job": "créatrice de contenu et infirmière aussi haha",
    "single": "célibataire malheureusment 😪"
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

def is_pure_et_toi(text: str) -> bool:
    t = (text or "").strip().lower()
    t = re.sub(r"[^\w\s?]", "", t)  # enlève ponctuation sauf ?
    t = t.strip()
    return t in {"et toi", "et toi ?", "toi ?", "toi", "toi aussi", "toi aussi ?"}

def answer_et_toi(last_slot: str | None) -> str:
    if last_slot == "prenom":
        return f"Moi c’est {BOT_PROFILE['name']} 😌"
    if last_slot == "ville":
        return f"Je suis de {BOT_PROFILE['city']}."
    if last_slot == "age":
        return f"J’ai {BOT_PROFILE['age']} ans."
    if last_slot == "metier":
        return f"Je suis {BOT_PROFILE['job']}."
    if last_slot == "celibataire":
        return f"Je suis {BOT_PROFILE['single']} 😏"
    return f"Moi c’est {BOT_PROFILE['name']} 😌"

def _load_script():
    with open(SCRIPT_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

async def _log_staff(bot, topic_id: int, text: str):
    if not STAFF_GROUP_ID or not topic_id:
        return
    try:
        await bot.request("sendMessage", {
            "chat_id": STAFF_GROUP_ID,
            "message_thread_id": topic_id,
            "text": text
        })
    except Exception as e:
        print(f"❌ [AI] log staff failed: {e}")

def sanitize_slot_value(slot: str, text: str) -> str:
    t = (text or "").strip()

    # enlève tout ce qui suit une forme "et toi"
    t = re.split(r"\bet toi\b|\btoi aussi\b", t, flags=re.IGNORECASE)[0].strip()

    # enlève ponctuation finale
    t = re.sub(r"[?!.,;:]+$", "", t).strip()

    # règles spécifiques
    if slot == "prenom":
        t = t.split()[0] if t else t
        if t:
            t = t[0].upper() + t[1:].lower()

    return t


# ---------------- Load script at startup ----------------
try:
    SCRIPT = _load_script()
except Exception as e:
    print(f"❌ [AI] Impossible de charger le script {SCRIPT_PATH}: {e}")
    SCRIPT = None


async def maybe_run_autopilot(message: types.Message, topic_id: int, bot):
    # 1) TEXT ONLY
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
    pure_et_toi = is_pure_et_toi(user_text)

    # 6) If waiting for a slot: handle answer (or “et toi ?” without answer)
    waiting_slot = profile.get("__waiting_slot")

    if waiting_slot:
        last_slot = profile.get("__last_question_slot") or waiting_slot

        # Cas: "et toi ?" seul -> on répond ET on repose la même question (NE PAS avancer)
        if asked and pure_et_toi:
            et_toi_reply = answer_et_toi(last_slot)

            current_step = steps[step_index]
            messages = current_step.get("messages") or []
            msg_out = random.choice(messages) if messages else "😌"
            msg_out = _render(msg_out, profile)

            final_out = f"{et_toi_reply} {msg_out}".strip()

            await bot.send_message(user_id, final_out)
            await _log_staff(bot, topic_id, f"[AUTO][ET_TOI][REASK][STEP {step_index}] → {final_out}")

            upsert_state(user_id, {
                "Cooldown Until": (now + datetime.timedelta(seconds=COOLDOWN_SECONDS)).isoformat()
            })
            return

        # Sinon: on essaie de remplir réellement le slot (réponse normale OU "xxx et toi ?")
        filled = False

        if waiting_slot == "age":
            age = _extract_age(user_text)
            if age is not None:
                profile["age"] = age
                filled = True
                if age < 18:
                    await bot.send_message(user_id, "Désolé, je ne peux pas continuer.")
                    upsert_state(user_id, {
                        "Autopilot": "OFF",
                        "Profile JSON": json.dumps(profile, ensure_ascii=False),
                        "Cooldown Until": (now + datetime.timedelta(seconds=COOLDOWN_SECONDS)).isoformat()
                    })
                    return

        elif waiting_slot == "celibataire":
            yn = _normalize_yes_no(user_text)
            profile["celibataire"] = yn if yn else user_text
            filled = True

        else:
            clean = sanitize_slot_value(waiting_slot, user_text)
            if clean:
                profile[waiting_slot] = clean
                filled = True

        # Si pas rempli, on repose la question (NE PAS avancer)
        if not filled:
            current_step = steps[step_index]
            messages = current_step.get("messages") or []
            msg_out = random.choice(messages) if messages else "😌"
            msg_out = _render(msg_out, profile)

            await bot.send_message(user_id, msg_out)
            await _log_staff(bot, topic_id, f"[AUTO][REASK][STEP {step_index}] → {msg_out}")

            upsert_state(user_id, {
                "Cooldown Until": (now + datetime.timedelta(seconds=COOLDOWN_SECONDS)).isoformat()
            })
            return

        # ✅ Slot rempli -> si le message contenait aussi "et toi ?", on veut répondre AVANT d'enchaîner
        if asked:
            profile["__prefix_next"] = answer_et_toi(last_slot)

        # Slot rempli -> on avance IMMEDIATEMENT et on continue dans le même tour
        profile["__waiting_slot"] = None
        step_index = min(step_index + 1, len(steps) - 1)

        upsert_state(user_id, {
            "Profile JSON": json.dumps(profile, ensure_ascii=False),
            "Step Index": step_index
        })

    # 7) Build step message (current step)
    current_step = steps[step_index]
    slot = current_step.get("slot")
    messages = current_step.get("messages") or []
    msg_out = random.choice(messages) if messages else "😌"
    msg_out = _render(msg_out, profile)

    # ✅ Si on a une réponse “et toi ?” stockée (cas "xxx et toi ?"), on la préfixe ici
    prefix = profile.pop("__prefix_next", None)
    if prefix:
        msg_out = f"{prefix} {msg_out}".strip()
        upsert_state(user_id, {"Profile JSON": json.dumps(profile, ensure_ascii=False)})

    # 8) If asked “et toi ?” (and not pure-only handled earlier), answer contextually + continue
    # Ici on garde cette logique pour les messages HORS waiting_slot (ex: il est déjà en phase libre)
    final_out = msg_out
    if asked and not waiting_slot:
        last_slot = profile.get("__last_question_slot") or slot
        final_out = f"{answer_et_toi(last_slot)} {msg_out}".strip()

    # send to client
    await bot.send_message(user_id, final_out)

    # log staff
    await _log_staff(bot, topic_id, f"[AUTO][STEP {step_index}] → {final_out}")

    # 9) Update waiting slot / last slot
    if slot:
        profile["__waiting_slot"] = slot
        profile["__last_question_slot"] = slot
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
