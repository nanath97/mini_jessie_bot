import os
import json
import random
import re
import datetime
from ai_state_store import get_state, upsert_state
from aiogram import types
import asyncio
import random




async def human_delay(min_s=6, max_s=15):
    await asyncio.sleep(random.uniform(min_s, max_s))

# ---------------- CONFIG ----------------
STAFF_GROUP_ID = int(os.getenv("STAFF_GROUP_ID", "0"))
COOLDOWN_SECONDS = 8

# Exemple: "script_fr_v1.json" (à la racine) ou "scripts/script_fr_v1.json"
SCRIPT_PATH = os.getenv("AI_SCRIPT_PATH", "script_fr_v1.json")

BOT_PROFILE = {
    "name": "Jessie",
    "city": "Haute-Savoie, dans les montagnes haha",
    "age": "23",
    "job": "créatrice de contenu et infirmière aussi haha",
    "single": "célibataire malheureusement 😪",
}

SOFT_ACKS = [
    "Ah ok 😌",
    "Je vois 😊",
    "D’accord 😌",
    "Mmh… 😏",
    "Intéressant 😉",
    "J’aime bien 🤭",
]


# ---------------- Small helpers ----------------
def pick_soft_ack(profile: dict) -> str:
    last = profile.get("__last_ack")
    choices = [a for a in SOFT_ACKS if a != last] or SOFT_ACKS
    ack = random.choice(choices)
    profile["__last_ack"] = ack
    return ack


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


def starts_like_et_toi(text: str) -> bool:
    t = (text or "").strip().lower()
    return bool(re.match(r"^(et\s+toi|toi)\b", t))


def detect_et_toi_target_slot(text: str) -> str | None:
    """
    Quand le client écrit "Et toi tu as quel âge ?" -> cible = "age"
    """
    t = (text or "").strip().lower()

    # âge
    if "âge" in t or "age" in t or "ans" in t:
        return "age"

    # ville / origine
    if ("viens" in t or "originaire" in t) and ("où" in t or "ou" in t):
        return "ville"

    # métier
    if "tu fais quoi" in t or "boulot" in t or "travail" in t or "métier" in t or "metier" in t:
        return "metier"

    # célibat
    if "célib" in t or "celib" in t or "en couple" in t or "t'es pris" in t or "t’es pris" in t:
        return "celibataire"

    # prénom
    if "prénom" in t or "prenom" in t or "tu t'appelles" in t or "tu t’appelles" in t or "ton nom" in t:
        return "prenom"

    return None


def answer_et_toi(slot: str | None) -> str:
    if slot == "prenom":
        return f"Moi c’est {BOT_PROFILE['name']} 😌"
    if slot == "ville":
        return f"Je suis de {BOT_PROFILE['city']}."
    if slot == "age":
        return f"J’ai {BOT_PROFILE['age']} ans."
    if slot == "metier":
        return f"Je suis {BOT_PROFILE['job']}."
    if slot == "celibataire":
        return f"Je suis {BOT_PROFILE['single']} 😏"
    return f"Moi c’est {BOT_PROFILE['name']} 😌"


def sanitize_slot_value(slot: str, text: str) -> str:
    """
    Ex: "Nathan et toi ?" -> "Nathan"
    Ex: "Garagiste et toi ?" -> "Garagiste"
    """
    t = (text or "").strip()

    # enlève tout ce qui suit une forme "et toi" / "toi aussi"
    t = re.split(r"\bet toi\b|\btoi aussi\b", t, flags=re.IGNORECASE)[0].strip()

    # enlève ponctuation finale
    t = re.sub(r"[?!.,;:]+$", "", t).strip()

    if slot == "prenom":
        t = t.split()[0] if t else t
        if t:
            t = t[0].upper() + t[1:].lower()

    return t


def remember_filled_slot(profile: dict, slot: str):
    profile["__last_filled_slot"] = slot
    filled = profile.get("__filled_slots")
    if not isinstance(filled, list):
        filled = []
    if slot not in filled:
        filled.append(slot)
    profile["__filled_slots"] = filled


def pick_step_message(step: dict, profile: dict, mode: str = "ask") -> str:
    """
    mode:
      - "ask"  -> step["messages"]
      - "reask"-> step["reask_messages"] si présent, sinon fallback
    """
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


async def _log_staff(bot, topic_id: int, text: str):
    if not STAFF_GROUP_ID or not topic_id:
        return
    try:
        await bot.request(
            "sendMessage",
            {
                "chat_id": STAFF_GROUP_ID,
                "message_thread_id": topic_id,
                "text": text,
            },
        )
    except Exception as e:
        print(f"❌ [AI] log staff failed: {e}")


# ---------------- Load script at startup ----------------
try:
    SCRIPT = _load_script()
except Exception as e:
    print(f"❌ [AI] Impossible de charger le script {SCRIPT_PATH}: {e}")
    SCRIPT = None


# ---------------- MAIN ----------------
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
        upsert_state(
            user_id,
            {
                "Topic ID": str(topic_id),
                "Script ID": SCRIPT.get("script_id", "script_fr_v1"),
                "Step Index": 0,
                "Profile JSON": "{}",
                "Heat": 0,
                "Pending Fillers JSON": "[]",
                "Autopilot": "OFF",
                "Cooldown Until": None,
            },
        )
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

    waiting_slot = profile.get("__waiting_slot")

    # ---------------- A) Waiting for a slot ----------------
    if waiting_slot:
        last_question_slot = profile.get("__last_question_slot") or waiting_slot
        pending = profile.get("__pending_et_toi_slot")

        # ✅ Cas important : "Et toi ..." (pas forcément "pur") pendant qu'on attend une réponse au slot.
        # Ex: "Et toi tu as quel âge ?" -> on répond à Jessie puis on REFORMULE la question EN COURS (waiting_slot)
        if asked and starts_like_et_toi(user_text) and not pure_et_toi:
            # Est-ce que le client a quand même répondu au slot en cours ?
            # (ex: "Garagiste et toi ?" -> sanitize renverra "Garagiste" donc on ne passe pas ici)
            clean_for_waiting = sanitize_slot_value(waiting_slot, user_text)

            if not clean_for_waiting:
                target = (
                    detect_et_toi_target_slot(user_text)
                    or pending
                    or profile.get("__last_filled_slot")
                    or last_question_slot
                )

                et_toi_reply = answer_et_toi(target)

                current_step = steps[step_index]
                msg_out = pick_step_message(current_step, profile, mode="reask")

                final_out = f"{et_toi_reply} {msg_out}".strip()

                await human_delay()
                await bot.send_message(user_id, final_out)
                await _log_staff(bot, topic_id, f"[AUTO][ET_TOI][FOLLOWUP][STEP {step_index}] → {final_out}")

                # on consomme le pending si on vient de l'utiliser
                profile.pop("__pending_et_toi_slot", None)

                upsert_state(
                    user_id,
                    {
                        "Profile JSON": json.dumps(profile, ensure_ascii=False),
                        "Cooldown Until": (now + datetime.timedelta(seconds=COOLDOWN_SECONDS)).isoformat(),
                    },
                )
                return

        # Cas: "et toi ?" seul -> on répond, puis on reformule la question actuelle (NE PAS avancer)
        if asked and pure_et_toi:
            et_toi_slot = pending or last_question_slot
            et_toi_reply = answer_et_toi(et_toi_slot)

            if pending:
                profile.pop("__pending_et_toi_slot", None)

            current_step = steps[step_index]
            msg_out = pick_step_message(current_step, profile, mode="reask")

            final_out = f"{et_toi_reply} {msg_out}".strip()
            await human_delay()
            await bot.send_message(user_id, final_out)
            await _log_staff(bot, topic_id, f"[AUTO][ET_TOI][REASK][STEP {step_index}] → {final_out}")

            upsert_state(
                user_id,
                {
                    "Profile JSON": json.dumps(profile, ensure_ascii=False),
                    "Cooldown Until": (now + datetime.timedelta(seconds=COOLDOWN_SECONDS)).isoformat(),
                },
            )
            return

        # Sinon: on essaie de remplir réellement le slot (réponse normale OU "xxx et toi ?")
        filled = False

        if waiting_slot == "age":
            age = _extract_age(user_text)
            if age is not None:
                profile["age"] = age
                filled = True
                remember_filled_slot(profile, waiting_slot)

                # si le client n'a PAS écrit "et toi ?" dans ce même message,
                # on garde le slot en pending pour le prochain "et toi ?"
                if not asked:
                    profile["__pending_et_toi_slot"] = waiting_slot
                else:
                    profile.pop("__pending_et_toi_slot", None)

                if age < 18:
                    await human_delay()
                    await bot.send_message(user_id, "Désolé, je ne peux pas continuer.")
                    upsert_state(
                        user_id,
                        {
                            "Autopilot": "OFF",
                            "Profile JSON": json.dumps(profile, ensure_ascii=False),
                            "Cooldown Until": (now + datetime.timedelta(seconds=COOLDOWN_SECONDS)).isoformat(),
                        },
                    )
                    return

        elif waiting_slot == "celibataire":
            yn = _normalize_yes_no(user_text)
            profile["celibataire"] = yn if yn else user_text
            filled = True
            remember_filled_slot(profile, waiting_slot)

            if not asked:
                profile["__pending_et_toi_slot"] = waiting_slot
            else:
                profile.pop("__pending_et_toi_slot", None)

        else:
            clean = sanitize_slot_value(waiting_slot, user_text)
            if clean:
                profile[waiting_slot] = clean
                filled = True
                remember_filled_slot(profile, waiting_slot)

                if not asked:
                    profile["__pending_et_toi_slot"] = waiting_slot
                else:
                    profile.pop("__pending_et_toi_slot", None)

        # Si pas rempli, on repose la question (reask, pas identique)
        if not filled:
            current_step = steps[step_index]
            msg_out = pick_step_message(current_step, profile, mode="reask")
            await human_delay()
            await bot.send_message(user_id, msg_out)
            await _log_staff(bot, topic_id, f"[AUTO][REASK][STEP {step_index}] → {msg_out}")

            upsert_state(
                user_id,
                {
                    "Profile JSON": json.dumps(profile, ensure_ascii=False),
                    "Cooldown Until": (now + datetime.timedelta(seconds=COOLDOWN_SECONDS)).isoformat(),
                },
            )
            return

        # ✅ Slot rempli -> prefix doux + éventuellement réponse "et toi ?" dans le même message
        ack = pick_soft_ack(profile)

        prefix_parts = []
        if asked:
            # si "xxx et toi ?" dans le même message, on répond au sujet du slot qu'on vient de remplir
            prefix_parts.append(answer_et_toi(waiting_slot))
        prefix_parts.append(ack)

        profile["__prefix_next"] = " ".join(prefix_parts).strip()

        # avancer au step suivant
        profile["__waiting_slot"] = None
        step_index = min(step_index + 1, len(steps) - 1)

        upsert_state(
            user_id,
            {
                "Profile JSON": json.dumps(profile, ensure_ascii=False),
                "Step Index": step_index,
            },
        )

    # ---------------- B) Build & send current step ----------------
    current_step = steps[step_index]
    slot = current_step.get("slot")

    msg_out = pick_step_message(current_step, profile, mode="ask")

    # Préfixe stocké (réaction + éventuellement réponse et-toi dans le même message précédent)
    prefix = profile.pop("__prefix_next", None)
    if prefix:
        msg_out = f"{prefix} {msg_out}".strip()
        upsert_state(user_id, {"Profile JSON": json.dumps(profile, ensure_ascii=False)})

    # Si "et toi ?" hors waiting_slot, on répond sur la dernière info remplie (ou la dernière question)
    final_out = msg_out
    if asked and not waiting_slot:
        et_toi_slot = profile.get("__last_filled_slot") or profile.get("__last_question_slot") or slot
        final_out = f"{answer_et_toi(et_toi_slot)} {msg_out}".strip()
    await human_delay()
    await bot.send_message(user_id, final_out)
    await _log_staff(bot, topic_id, f"[AUTO][STEP {step_index}] → {final_out}")

    # Mettre le bot en attente de réponse si c'est un slot
    if slot:
        profile["__waiting_slot"] = slot
        profile["__last_question_slot"] = slot
        upsert_state(
            user_id,
            {
                "Profile JSON": json.dumps(profile, ensure_ascii=False),
                "Step Index": step_index,
            },
        )
    else:
        upsert_state(user_id, {"Step Index": step_index + 1})

    # Cooldown
    upsert_state(
        user_id,
        {
            "Cooldown Until": (now + datetime.timedelta(seconds=COOLDOWN_SECONDS)).isoformat(),
        },
    )
