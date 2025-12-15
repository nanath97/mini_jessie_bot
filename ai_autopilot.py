import os
import json
import random
import re
import datetime
from ai_state_store import get_state, upsert_state
from aiogram import types
import asyncio


async def human_delay(min_s=6, max_s=15):
    await asyncio.sleep(random.uniform(min_s, max_s))


# ---------------- CONFIG ----------------
STAFF_GROUP_ID = int(os.getenv("STAFF_GROUP_ID", "0"))
COOLDOWN_SECONDS = 8

# Exemple: "script_fr_v1.json" (à la racine) ou "scripts/script_fr_v1.json"
SCRIPT_PATH = os.getenv("AI_SCRIPT_PATH", "script_fr_v1.json")

# Glue-layer
SAFE_TURNS_LIMIT = 15
COOLDOWN_MINUTES_ON_SAFE_LIMIT = 30

# Anti-spam SHIFT / OFFER
SHIFT_MIN_SECONDS_BETWEEN = 90
OFFER_COOLDOWN_SECONDS = 180

# Offer config
OFFER_MIN_PALIER = 4  # déclenche l'offre à partir de palier 4

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

# SHIFT 1: vibe (changement d’énergie, 0 question)
SHIFT_VIBE_MESSAGES = [
    "Ok je vois 😌",
    "Haha j’avoue 🤭",
    "T’es marrant toi 😏",
    "J’aime bien ton énergie 😌",
    "Mmh intéressant… 😏",
    "Ok… ça devient intriguant 😌",
]

# SHIFT 2: curiosity (1 question légère max)
SHIFT_CURIOSITY_TEMPLATES = [
    "Ok 😌 et toi t’es plutôt {topic_a} ou {topic_b} ?",
    "Haha 😏 dis-moi, t’es plus {topic_a} ou {topic_b} ?",
    "Je vois 😊 t’es team {topic_a} ou team {topic_b} ?",
]

# SHIFT 3: pre-offer (pas de lien ici: préparation)
SHIFT_PREOFFER_MESSAGES = [
    "Ok 😏 je te dis un truc…",
    "Mmh… je peux te montrer un truc mais faut être sage 😌",
    "Haha 😌 attends… j’ai un truc en tête là.",
    "Ok… on va peut-être passer à un niveau au-dessus 😏",
]

CURIOSITY_TOPICS = [
    ("ciné", "séries"),
    ("matin", "nuit"),
    ("voyage", "soirée chill"),
    ("surprise", "mystère"),
    ("soft", "taquin"),
    ("blanc", "rouge"),
]


# ---------------- Small helpers ----------------
def pick_soft_ack(profile: dict) -> str:
    last = profile.get("__last_ack")
    choices = [a for a in SOFT_ACKS if a != last] or SOFT_ACKS
    ack = random.choice(choices)
    profile["__last_ack"] = ack
    return ack


def _pick_nonrepeat(profile: dict, key: str, pool: list[str]) -> str:
    last = profile.get(key)
    choices = [x for x in pool if x != last] or pool
    msg = random.choice(choices)
    profile[key] = msg
    return msg


def pick_shift_vibe(profile: dict) -> str:
    return _pick_nonrepeat(profile, "__last_shift_vibe", SHIFT_VIBE_MESSAGES)


def pick_shift_preoffer(profile: dict) -> str:
    return _pick_nonrepeat(profile, "__last_shift_preoffer", SHIFT_PREOFFER_MESSAGES)


def pick_shift_curiosity(profile: dict) -> str:
    tpl = _pick_nonrepeat(profile, "__last_shift_cur_tpl", SHIFT_CURIOSITY_TEMPLATES)
    a, b = random.choice(CURIOSITY_TOPICS)
    return tpl.format(topic_a=a, topic_b=b)


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
    yes = {
        "oui", "ouais", "yep", "yeah", "si", "claro", "ok",
        "daccord", "d'accord", "bien sur", "bien sûr"
    }
    no = {"non", "nope", "nan", "pas", "pas du tout"}
    if any(x == t or x in t for x in yes):
        return "oui"
    if any(x == t or x in t for x in no):
        return "non"
    return None


# ---------------- Glue Layer V1: signal detection ----------------
def detect_desire_signal(text: str) -> bool:
    if not text:
        return False
    t = text.lower()
    patterns = [
        r"\bsexy\b", r"\bhot\b", r"\bcanon\b", r"\bjolie\b", r"\bbelle\b",
        r"\bcharmante\b", r"\btu me plais\b",
        r"\bexcite\b", r"\bexcité\b", r"\bj'ai envie\b", r"\bça m'excite\b",
        r"\btu me chauffes\b",
    ]
    return any(re.search(p, t) for p in patterns)


def detect_buyer_signal(text: str) -> bool:
    if not text:
        return False
    t = text.lower()
    patterns = [
        r"\bphoto\b", r"\bvideo\b", r"\bvidéo\b", r"\bvoir\b", r"\bmontre\b", r"\benvoie\b",
        r"\blien\b", r"\bprix\b", r"\bcombien\b", r"\bça coûte\b", r"\bcoute\b",
        r"\bvip\b",
    ]
    return any(re.search(p, t) for p in patterns)


def should_offer_tier(profile: dict, buyer_signal: bool, desire_signal: bool) -> bool:
    palier = int(profile.get("palier") or 1)
    if palier >= OFFER_MIN_PALIER and buyer_signal:
        return True
    # Option future (si tu veux): palier 4 + désir très fort
    # if palier >= OFFER_MIN_PALIER and desire_signal:
    #     return True
    return False


# ---------------- “Et toi” helpers ----------------
def is_et_toi(text: str) -> bool:
    t = (text or "").strip().lower()
    return ("et toi" in t) or ("toi ?" in t) or ("toi aussi" in t)


def is_pure_et_toi(text: str) -> bool:
    t = (text or "").strip().lower()
    t = re.sub(r"[^\w\s?]", "", t).strip()
    return t in {"et toi", "et toi ?", "toi ?", "toi", "toi aussi", "toi aussi ?"}


def starts_like_et_toi(text: str) -> bool:
    t = (text or "").strip().lower()
    return bool(re.match(r"^(et\s+toi|toi)\b", t))


def detect_et_toi_target_slot(text: str) -> str | None:
    t = (text or "").strip().lower()
    if "âge" in t or "age" in t or "ans" in t:
        return "age"
    if ("viens" in t or "originaire" in t) and ("où" in t or "ou" in t):
        return "ville"
    if "tu fais quoi" in t or "boulot" in t or "travail" in t or "métier" in t or "metier" in t:
        return "metier"
    if "célib" in t or "celib" in t or "en couple" in t or "t'es pris" in t or "t’es pris" in t:
        return "celibataire"
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
    t = (text or "").strip()
    t = re.split(r"\bet toi\b|\btoi aussi\b", t, flags=re.IGNORECASE)[0].strip()
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

    # defaults (no migration required)
    profile.setdefault("safe_turns", 0)
    profile.setdefault("phase", "S5")
    profile.setdefault("palier", 1)

    steps = SCRIPT["steps"]
    step_index = int(fields.get("Step Index") or 0)
    step_index = max(0, min(step_index, len(steps) - 1))

    user_text = (message.text or "").strip()
    asked = is_et_toi(user_text)
    pure_et_toi = is_pure_et_toi(user_text)
    waiting_slot = profile.get("__waiting_slot")

    # signals
    desire_signal = detect_desire_signal(user_text)
    buyer_signal = detect_buyer_signal(user_text)

    # safe turns
    if desire_signal or buyer_signal:
        profile["safe_turns"] = 0
    else:
        profile["safe_turns"] = int(profile.get("safe_turns") or 0) + 1

    # Decide action
    action = "A_CONVERSE"
    if profile["safe_turns"] >= SAFE_TURNS_LIMIT:
        action = "A_COOLDOWN"
    elif should_offer_tier(profile, buyer_signal, desire_signal):
        action = "A_OFFER_TIER"
    elif buyer_signal:
        action = "A_SHIFT"

    # --- A_COOLDOWN ---
    if action == "A_COOLDOWN":
        upsert_state(
            user_id,
            {
                "Profile JSON": json.dumps(profile, ensure_ascii=False),
                "Cooldown Until": (now + datetime.timedelta(minutes=COOLDOWN_MINUTES_ON_SAFE_LIMIT)).isoformat(),
            },
        )
        return

    # --- A_OFFER_TIER (HOOK COMPLET) ---
    # Déclenche une "offre" uniquement quand palier >= 4 + buyer_signal
    # Ici on met un placeholder pour vérifier que la mécanique marche.
    if action == "A_OFFER_TIER" and not waiting_slot:
        last_offer_ts_str = profile.get("__last_offer_ts")
        last_offer_ts = _parse_airtable_dt(last_offer_ts_str) if last_offer_ts_str else None

        if last_offer_ts and (now - last_offer_ts).total_seconds() < OFFER_COOLDOWN_SECONDS:
            action = "A_CONVERSE"
        else:
            tier_to_offer = int(profile.get("palier") or OFFER_MIN_PALIER)
            tier_to_offer = max(1, min(tier_to_offer, 4))

            profile["__last_offer_ts"] = now.isoformat()
            profile["safe_turns"] = 0
            profile["__pending_offer_tier"] = tier_to_offer

            # Placeholder neutre (à remplacer demain par lien Stripe + bouton)
            offer_placeholder = f"[OFFER_TIER_HOOK] tier={tier_to_offer}"

            await human_delay()
            await bot.send_message(user_id, offer_placeholder)
            await _log_staff(bot, topic_id, f"[AUTO][OFFER_TIER][T{tier_to_offer}] → {offer_placeholder}")

            upsert_state(
                user_id,
                {
                    "Profile JSON": json.dumps(profile, ensure_ascii=False),
                    "Cooldown Until": (now + datetime.timedelta(seconds=COOLDOWN_SECONDS)).isoformat(),
                },
            )
            return

    # --- A_SHIFT (3 variantes) ---
    if action == "A_SHIFT" and not waiting_slot:
        last_shift_ts_str = profile.get("__last_shift_ts")
        last_shift_ts = _parse_airtable_dt(last_shift_ts_str) if last_shift_ts_str else None

        if last_shift_ts and (now - last_shift_ts).total_seconds() < SHIFT_MIN_SECONDS_BETWEEN:
            action = "A_CONVERSE"
        else:
            palier = int(profile.get("palier") or 1)
            palier = max(1, min(palier, 4))

            # Choix variante:
            # - palier 1-2: vibe / curiosity
            # - palier 3: curiosity / preoffer
            # - palier 4: preoffer (préparation)
            if palier <= 2:
                variant = "SHIFT_CURIOSITY" if (profile["safe_turns"] >= 8) else "SHIFT_VIBE"
            elif palier == 3:
                variant = "SHIFT_PREOFFER" if (desire_signal or buyer_signal) else "SHIFT_CURIOSITY"
            else:
                variant = "SHIFT_PREOFFER"

            if variant == "SHIFT_VIBE":
                shift_msg = pick_shift_vibe(profile)
            elif variant == "SHIFT_CURIOSITY":
                shift_msg = pick_shift_curiosity(profile)
            else:
                shift_msg = pick_shift_preoffer(profile)
                # progression palier (cap à 4)
                profile["palier"] = min(4, palier + 1)

            profile["__last_shift_ts"] = now.isoformat()
            profile["safe_turns"] = 0

            await human_delay()
            await bot.send_message(user_id, shift_msg)
            await _log_staff(
                bot,
                topic_id,
                f"[AUTO][SHIFT][{variant}][PALIER {profile.get('palier', palier)}] → {shift_msg}",
            )

            upsert_state(
                user_id,
                {
                    "Profile JSON": json.dumps(profile, ensure_ascii=False),
                    "Cooldown Until": (now + datetime.timedelta(seconds=COOLDOWN_SECONDS)).isoformat(),
                },
            )
            return

    # ---------------- A) Waiting for a slot ----------------
    if waiting_slot:
        last_question_slot = profile.get("__last_question_slot") or waiting_slot
        pending = profile.get("__pending_et_toi_slot")

        # ✅ Cas important : "Et toi ..." (pas forcément "pur") pendant qu'on attend une réponse au slot.
        if asked and starts_like_et_toi(user_text) and not pure_et_toi:
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

                profile.pop("__pending_et_toi_slot", None)
                upsert_state(
                    user_id,
                    {
                        "Profile JSON": json.dumps(profile, ensure_ascii=False),
                        "Cooldown Until": (now + datetime.timedelta(seconds=COOLDOWN_SECONDS)).isoformat(),
                    },
                )
                return

        # Cas: "et toi ?" seul
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

        # Sinon: on essaie de remplir le slot
        filled = False

        if waiting_slot == "age":
            age = _extract_age(user_text)
            if age is not None:
                profile["age"] = age
                filled = True
                remember_filled_slot(profile, waiting_slot)

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

        # Pas rempli -> reask
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

        # Slot rempli -> prefix doux (+ réponse et toi si présent)
        ack = pick_soft_ack(profile)
        prefix_parts = []
        if asked:
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

    prefix = profile.pop("__prefix_next", None)
    if prefix:
        msg_out = f"{prefix} {msg_out}".strip()
        upsert_state(user_id, {"Profile JSON": json.dumps(profile, ensure_ascii=False)})

    final_out = msg_out
    if asked and not waiting_slot:
        et_toi_slot = profile.get("__last_filled_slot") or profile.get("__last_question_slot") or slot
        final_out = f"{answer_et_toi(et_toi_slot)} {msg_out}".strip()

    await human_delay()
    await bot.send_message(user_id, final_out)
    await _log_staff(bot, topic_id, f"[AUTO][STEP {step_index}] → {final_out}")

    # Set waiting slot if needed
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

    # Cooldown classique
    upsert_state(
        user_id,
        {
            "Profile JSON": json.dumps(profile, ensure_ascii=False),
            "Cooldown Until": (now + datetime.timedelta(seconds=COOLDOWN_SECONDS)).isoformat(),
        },
    )
