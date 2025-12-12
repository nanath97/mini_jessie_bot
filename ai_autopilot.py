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
    "single": "célibataire malheureusement 😪"
}

SOFT_ACKS = [
    "Ah ok 😌",
    "Je vois 😊",
    "D’accord 😌",
    "Mmh… 😏",
    "Intéressant 😉",
    "J’aime bien 😌",
]


# ---------------- Small helpers ----------------
def pick_soft_ack(profile: dict) -> str:
    last = profile.get("__last_ack")
    choices = [a for a in SOFT_ACKS if a != last] or SOFT_ACKS
    ack = random.choice(choices)
    profile["__last_ack"] = ack
    return ack


def remember_filled_slot(profile: dict, slot: str):
    profile["__last_filled_slot"] = slot
    filled = profile.get("__filled_slots")
    if not isinstance(filled, list):
        filled = []
    if slot not in filled:
        filled.append(slot)
    profile["__filled_slots"] = filled


def get_et_toi_slot(profile: dict, fallback_slot: str | None) -> str | None:
    return profile.get("__last_filled_slot") or profile.get("__last_question_slot") or fallback_slot


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
    t = re.sub(r"[^\w\s?]", "", t)
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


def sanitize_slot_value(slot: str, text: str) -> str:
    t = (text or "").strip()

    # enlève tout ce qui suit une forme "et toi"
    t = re.split(r"\bet toi\b|\btoi aussi\b", t, flags=re.IGNORECASE)[0].strip()

    # enlève ponctuation finale
    t = re.sub(r"[?!.,;:]+$", "", t).strip()

    if slot == "prenom":
        t = t.split()[0] if t else t
        if t:
            t = t[0].upper() + t[1:].lower()

    return t


def pick_step_message(step: dict, profile: dict, mode: str = "ask") -> str:
    if mode == "reask":
        msgs = step.get("reask_messages") or []
        if msgs:
            return _render(random.choice(msgs), profile)

        slot = step.get("slot")
        fallback = {
            "prenom": [
                "Au fait… tu t’appelles comment ? 😌",
                "Dis-moi ton prénom 😊",
                "Je peux savoir ton prénom ? 😌",
            ],
            "ville": [
                "Tu viens d’où exactement ? 😊",
                "T’es de quelle ville ? 😌",
                "Tu vis où en ce moment ? 😌",
            ],
            "age": [
                "Tu as quel âge déjà ? 😌",
                "Tu peux me dire ton âge ? 😊",
                "J’ai pas capté ton âge 😅 tu me redis ?",
            ],
            "metier": [
                "Et toi, tu fais quoi dans la vie exactement ? 😌",
                "Tu bosses dans quoi ? 😊",
                "Tu fais quoi comme boulot ? 😌",
            ],
            "celibataire": [
                "Et toi… t’es célibataire ou déjà pris ? 😏",
                "Dis-moi… t’es plutôt libre ou tu as quelqu’un ? 😌",
                "T’es en couple ou solo en ce moment ? 😏",
            ],
        }
        candidates = fallback.get(slot) or (step.get("messages") or [])
        return _render(random.choice(candidates) if candidates else "😌", profile)

    msgs = step.get("messages") or []
    return _render(random.choice(msgs) if msgs else "😌", profile)


def _load_script():
    with open(SCRIPT_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


# ---------------- Load script at startup ----------------
try:
    SCRIPT = _load_script()
except Exception as e:
    print(f"❌ [AI] Impossible de charger le script {SCRIPT_PATH}: {e}")
    SCRIPT = None


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


# ---------------- Main entry ----------------
async def maybe_run_autopilot(message: types.Message, topic_id: int, bot):
    if message.content_type != types.ContentType.TEXT:
        return

    if not SCRIPT or "steps" not in SCRIPT:
        return

    user_id = message.from_user.id
    now = _utcnow()

    state = get_state(user_id)

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

    if fields.get("Autopilot") != "ON":
        return

    cooldown_str = fields.get("Cooldown Until")
    cd_time = _parse_airtable_dt(cooldown_str) if cooldown_str else None
    if cd_time and now < cd_time:
        return

    profile = _safe_json_loads(fields.get("Profile JSON"), {})
    if not isinstance(profile, dict):
        profile = {}

    steps = SCRIPT["steps"]
    step_index = int(fields.get("Step Index") or 0)
    step_index = max(0, min(step_index, len(steps) - 1))

    user_text = (message.text or "").strip()
    asked = is_et_toi(user_text)
    pure_et_toi = is_pure_et_toi(user_text)

    waiting_slot = profile.get("__waiting_slot")

    # ---------------- Waiting slot flow ----------------
    if waiting_slot:
        # Slot auquel on répond si le client dit "et toi ?" (priorité: dernier slot rempli)
        et_toi_slot = get_et_toi_slot(profile, waiting_slot)

        # Cas: "et toi ?" seul -> on répond + on REPOSE (variante)
        if asked and pure_et_toi:
            et_toi_reply = answer_et_toi(et_toi_slot)

            current_step = steps[step_index]
            msg_out = pick_step_message(current_step, profile, mode="reask")
            final_out = f"{et_toi_reply} {msg_out}".strip()

            await bot.send_message(user_id, final_out)
            await _log_staff(bot, topic_id, f"[AUTO][ET_TOI][REASK][STEP {step_index}] → {final_out}")

            upsert_state(user_id, {
                "Profile JSON": json.dumps(profile, ensure_ascii=False),
                "Cooldown Until": (now + datetime.timedelta(seconds=COOLDOWN_SECONDS)).isoformat()
            })
            return

        # Sinon: on tente de remplir le slot (réponse normale OU "xxx et toi ?")
        filled = False

        if waiting_slot == "age":
            age = _extract_age(user_text)
            if age is not None:
                profile["age"] = age
                filled = True
                remember_filled_slot(profile, waiting_slot)
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
            remember_filled_slot(profile, waiting_slot)

        else:
            clean = sanitize_slot_value(waiting_slot, user_text)
            if clean:
                profile[waiting_slot] = clean
                filled = True
                remember_filled_slot(profile, waiting_slot)

        # Si pas rempli -> REASK variante
        if not filled:
            current_step = steps[step_index]
            msg_out = pick_step_message(current_step, profile, mode="reask")

            await bot.send_message(user_id, msg_out)
            await _log_staff(bot, topic_id, f"[AUTO][REASK][STEP {step_index}] → {msg_out}")

            upsert_state(user_id, {
                "Profile JSON": json.dumps(profile, ensure_ascii=False),
                "Cooldown Until": (now + datetime.timedelta(seconds=COOLDOWN_SECONDS)).isoformat()
            })
            return

        # ✅ Slot rempli -> prefix doux (et éventuellement réponse "et toi ?")
        ack = pick_soft_ack(profile)
        prefix_parts = []
        if asked:
            prefix_parts.append(answer_et_toi(et_toi_slot))
        prefix_parts.append(ack)
        profile["__prefix_next"] = " ".join(prefix_parts).strip()

        # On avance au step suivant
        profile["__waiting_slot"] = None
        step_index = min(step_index + 1, len(steps) - 1)

        upsert_state(user_id, {
            "Profile JSON": json.dumps(profile, ensure_ascii=False),
            "Step Index": step_index
        })

    # ---------------- Normal step send ----------------
    current_step = steps[step_index]
    slot = current_step.get("slot")
    msg_out = pick_step_message(current_step, profile, mode="ask")

    # préfixe stocké (réaction humaine + éventuellement réponse "et toi ?")
    prefix = profile.pop("__prefix_next", None)
    if prefix:
        msg_out = f"{prefix} {msg_out}".strip()
        upsert_state(user_id, {"Profile JSON": json.dumps(profile, ensure_ascii=False)})

    # Si "et toi ?" hors waiting_slot, on répond sur le meilleur slot puis on continue
    final_out = msg_out
    if asked and not waiting_slot:
        et_toi_slot = get_et_toi_slot(profile, slot)
        final_out = f"{answer_et_toi(et_toi_slot)} {msg_out}".strip()

    await bot.send_message(user_id, final_out)
    await _log_staff(bot, topic_id, f"[AUTO][STEP {step_index}] → {final_out}")

    # set waiting slot if needed
    if slot:
        profile["__waiting_slot"] = slot
        profile["__last_question_slot"] = slot
        upsert_state(user_id, {
            "Profile JSON": json.dumps(profile, ensure_ascii=False),
            "Step Index": step_index
        })
    else:
        upsert_state(user_id, {"Step Index": step_index + 1})

    upsert_state(user_id, {
        "Cooldown Until": (now + datetime.timedelta(seconds=COOLDOWN_SECONDS)).isoformat()
    })
