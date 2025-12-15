import os
import json
import random
import re
import datetime
import asyncio
import uuid
from ai_state_store import get_state, upsert_state
from aiogram import types

# OpenAI SDK (official)
from openai import OpenAI


# ---------------- LLM CONFIG ----------------
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
AI_MODEL = os.getenv("AI_MODEL", "gpt-4.1")
AI_TONE = os.getenv("AI_TONE", "fr")

LLM_MAX_OUTPUT_TOKENS = int(os.getenv("LLM_MAX_OUTPUT_TOKENS", "80"))
LLM_TIMEOUT_SECONDS = int(os.getenv("LLM_TIMEOUT_SECONDS", "20"))

# Debounce: regroupe les rafales de messages en une seule réponse
DEBOUNCE_SECONDS = float(os.getenv("AI_DEBOUNCE_SECONDS", "2.2"))

client = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None


async def human_delay(min_s=6, max_s=15):
    await asyncio.sleep(random.uniform(min_s, max_s))


# ---------------- CONFIG ----------------
STAFF_GROUP_ID = int(os.getenv("STAFF_GROUP_ID", "0"))
COOLDOWN_SECONDS = 8

SCRIPT_PATH = os.getenv("AI_SCRIPT_PATH", "script_fr_v1.json")

SAFE_TURNS_LIMIT = 15
COOLDOWN_MINUTES_ON_SAFE_LIMIT = 30

BOT_PROFILE = {
    "name": "Jessie",
    "city": "Haute-Savoie, dans les montagnes haha",
    "age": "23",
    "job": "créatrice de contenu et infirmière aussi haha",
    "single": "célibataire malheureusement 😪",
}


# ---------------- Small helpers ----------------
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


def _is_greeting(text: str) -> bool:
    t = (text or "").strip().lower()
    t = re.sub(r"[^\w\s]", "", t)
    return t in {"salut", "coucou", "hey", "yo", "hello", "cc", "slt", "bonjour"} or len(t) <= 3


# ---------------- Signal detection ----------------
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


# ---------------- “Et toi” helpers ----------------
def is_et_toi(text: str) -> bool:
    t = (text or "").strip().lower()
    return ("et toi" in t) or ("toi ?" in t) or ("toi aussi" in t)


def is_pure_et_toi(text: str) -> bool:
    t = (text or "").strip().lower()
    t = re.sub(r"[^\w\s?]", "", t).strip()
    return t in {"et toi", "et toi ?", "toi ?", "toi", "toi aussi", "toi aussi ?"}


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


# ---------------- Script loading (fallback only) ----------------
def _load_script():
    with open(SCRIPT_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


try:
    SCRIPT = _load_script()
except Exception as e:
    print(f"❌ [AI] Impossible de charger le script {SCRIPT_PATH}: {e}")
    SCRIPT = None


async def _log_staff(bot, topic_id: int, text: str):
    if not STAFF_GROUP_ID or not topic_id:
        return
    try:
        await bot.request(
            "sendMessage",
            {"chat_id": STAFF_GROUP_ID, "message_thread_id": topic_id, "text": text},
        )
    except Exception as e:
        print(f"❌ [AI] log staff failed: {e}")


# ---------------- LLM: Natural language generation ----------------
def _profile_public(profile: dict) -> dict:
    keep = {}
    for k, v in profile.items():
        if k.startswith("__"):
            continue
        if k in {"prenom", "age", "ville", "metier", "celibataire"}:
            keep[k] = v
    return keep


def _slot_label(slot: str) -> str:
    return {
        "prenom": "son prénom",
        "ville": "sa ville",
        "age": "son âge",
        "metier": "son métier",
        "celibataire": "son statut (célibataire/en couple)",
    }.get(slot, slot)


async def llm_generate(intent: str, slot: str | None, profile: dict, last_user_text: str) -> str | None:
    """
    intent:
      - presence: réponse humaine SANS question (Phase 0)
      - ask_slot: UNE question directe pour obtenir un slot
      - reask_slot: relance directe (pas de détour)
      - react_only: réponse humaine SANS question (après remplissage)
      - smalltalk: réponse libre (max 1 question)
    """
    if not client:
        return None

    user_profile = _profile_public(profile)
    have = ", ".join([f"{k}={v}" for k, v in user_profile.items()]) or "rien pour l’instant"
    target = _slot_label(slot) if slot else "rien"

    system = (
        "Tu t’appelles Jessie. "
        "Tu écris comme une vraie femme sur Telegram: naturelle, chaleureuse, un peu taquine (jamais robotique). "
        "Tu ne fais pas de détours bizarres. "
        "Style: 1 phrase, parfois 2 maximum. Pas de listes. 0 à 1 emoji. "
        "Interdit: mentionner IA/bot/script/API, paiement/prix/offre. "
        "Très important: ne fais pas d’affirmation sur une info que tu n’as pas."
    )

    if intent == "presence":
        instruction = (
            "Réponds de façon douce et humaine à un premier message. "
            "Interdit de poser une question. "
            f"Tu sais déjà: {have}."
        )
    elif intent == "ask_slot":
        instruction = (
            f"Pose UNE question simple, directe, assumée pour obtenir {target}. "
            "Pas de détour, pas de sous-questions. "
            f"Tu sais déjà: {have}."
        )
    elif intent == "reask_slot":
        instruction = (
            f"Relance UNE fois pour obtenir {target}, simplement. "
            "Pas de détour, pas de justification. "
            f"Tu sais déjà: {have}."
        )
    elif intent == "react_only":
        instruction = (
            "Réponds de façon humaine à son message SANS poser de question. "
            f"Tu sais déjà: {have}."
        )
    else:
        instruction = (
            "Réponds naturellement; si tu poses une question, UNE seule, vraiment naturelle. "
            f"Tu sais déjà: {have}."
        )

    prompt = (
        f"{instruction}\n\n"
        f"Dernier message du client: {last_user_text}\n"
        f"Réponds maintenant:"
    )

    try:
        def _call():
            r = client.responses.create(
                model=AI_MODEL,
                input=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": prompt},
                ],
                max_output_tokens=LLM_MAX_OUTPUT_TOKENS,
            )
            return (r.output_text or "").strip()

        text = await asyncio.wait_for(asyncio.to_thread(_call), timeout=LLM_TIMEOUT_SECONDS)
        text = re.sub(r"\s+", " ", text).strip()
        return text if text else None
    except Exception as e:
        print(f"❌ [LLM] generation failed: {e}")
        return None


def fallback_slot_question(slot: str, mode: str = "ask") -> str:
    if mode == "reask":
        if slot == "prenom":
            return "Au fait, ton prénom ? 😊"
        if slot == "ville":
            return "Tu viens d’où ? 😊"
        if slot == "age":
            return "Tu as quel âge ? 😊"
        if slot == "metier":
            return "Tu fais quoi dans la vie ? 😊"
        if slot == "celibataire":
            return "T’es plutôt libre ou en couple ? 😏"
        return "Dis-m’en un peu plus 😊"

    if slot == "prenom":
        return "Au fait, tu t’appelles comment ? 😊"
    if slot == "ville":
        return "Tu es de quelle ville ? 😊"
    if slot == "age":
        return "Tu as quel âge ? 😊"
    if slot == "metier":
        return "Tu fais quoi dans la vie ? 😊"
    if slot == "celibataire":
        return "T’es célibataire ou pris ? 😏"
    return "Dis-m’en un peu plus 😊"


# ---------------- Core flow helpers ----------------
SLOT_ORDER = ["prenom", "ville", "age", "metier", "celibataire"]


def _next_missing_slot(profile: dict) -> str | None:
    for s in SLOT_ORDER:
        if s not in profile:
            return s
    return None


def _inc_ai_turn(profile: dict):
    profile["__ai_turns"] = int(profile.get("__ai_turns") or 0) + 1


def _question_allowed(profile: dict) -> bool:
    # cooldown anti-interrogatoire: après une question, on force 1 tour sans question
    return int(profile.get("__q_cooldown") or 0) <= 0


def _set_question_cooldown(profile: dict, turns: int = 1):
    profile["__q_cooldown"] = turns


def _tick_question_cooldown(profile: dict):
    cd = int(profile.get("__q_cooldown") or 0)
    if cd > 0:
        profile["__q_cooldown"] = cd - 1


# ---------------- Debounce runner ----------------
async def _debounced_autopilot_run(user_id: int, topic_id: int, bot, token: str):
    """
    Attend la fin d'une rafale de messages, puis répond UNE seule fois.
    """
    await asyncio.sleep(DEBOUNCE_SECONDS)

    state = get_state(user_id)
    if not state:
        return
    fields = state.get("fields", {})
    if fields.get("Autopilot") != "ON":
        return

    profile = _safe_json_loads(fields.get("Profile JSON"), {})
    if not isinstance(profile, dict):
        profile = {}

    # si un nouveau message est arrivé, on annule (token différent)
    if profile.get("__debounce_token") != token:
        return

    now = _utcnow()

    # cooldown global
    cooldown_str = fields.get("Cooldown Until")
    cd_time = _parse_airtable_dt(cooldown_str) if cooldown_str else None
    if cd_time and now < cd_time:
        return

    # texte agrégé depuis la rafale
    bundle = profile.get("__bundle_text", "")
    last_user_text = (bundle or profile.get("__last_user_text") or "").strip()
    if not last_user_text:
        return

    # nettoyage bundle
    profile["__bundle_text"] = ""

    # sécurité: limite de tours "sans signal"
    profile.setdefault("safe_turns", 0)
    desire_signal = detect_desire_signal(last_user_text)
    buyer_signal = detect_buyer_signal(last_user_text)
    if desire_signal or buyer_signal:
        profile["safe_turns"] = 0
    else:
        profile["safe_turns"] = int(profile.get("safe_turns") or 0) + 1

    if profile["safe_turns"] >= SAFE_TURNS_LIMIT:
        upsert_state(
            user_id,
            {
                "Profile JSON": json.dumps(profile, ensure_ascii=False),
                "Cooldown Until": (now + datetime.timedelta(minutes=COOLDOWN_MINUTES_ON_SAFE_LIMIT)).isoformat(),
            },
        )
        return

    asked = is_et_toi(last_user_text)
    pure_et_toi = is_pure_et_toi(last_user_text)

    # tick anti-question
    _tick_question_cooldown(profile)

    # ---------------- PHASE PILOTED BY HANDLER ----------------
    # Règle dure : si prénom pas connu -> 2 messages présence (sans question),
    # puis 3e message bot = demande prénom DIRECTE.
    ai_turns = int(profile.get("__ai_turns") or 0)

    # Force Phase 0 / Phase 1 prénom
    if "prenom" not in profile:
        if ai_turns < 2:
            # Phase 0: présence (aucune question)
            msg_out = await llm_generate("presence", None, profile, last_user_text)
            if not msg_out:
                msg_out = "Coucou toi 😊" if _is_greeting(last_user_text) else "Hmm je vois 😊"

            await human_delay()
            await bot.send_message(user_id, msg_out)
            await _log_staff(bot, topic_id, f"[AUTO][P0][PRESENCE] → {msg_out}")

            _inc_ai_turn(profile)
            upsert_state(
                user_id,
                {
                    "Profile JSON": json.dumps(profile, ensure_ascii=False),
                    "Cooldown Until": (now + datetime.timedelta(seconds=COOLDOWN_SECONDS)).isoformat(),
                },
            )
            return

        # 3e message bot: demander le prénom (FIXE, pas LLM)
        profile["__waiting_slot"] = "prenom"
        profile["__last_question_slot"] = "prenom"
        _set_question_cooldown(profile, 1)

        # si le client dit "et toi ?" tout seul, on répond Jessie + demande prénom
        prefix = ""
        if asked and pure_et_toi:
            prefix = f"{answer_et_toi('prenom')} "

        msg_out = prefix + fallback_slot_question("prenom", "ask")

        await human_delay()
        await bot.send_message(user_id, msg_out)
        await _log_staff(bot, topic_id, f"[AUTO][P1][ASK_PRENOM] → {msg_out}")

        _inc_ai_turn(profile)
        upsert_state(
            user_id,
            {
                "Profile JSON": json.dumps(profile, ensure_ascii=False),
                "Cooldown Until": (now + datetime.timedelta(seconds=COOLDOWN_SECONDS)).isoformat(),
            },
        )
        return

    # ---------------- NORMAL SLOT FLOW (Phase 2) ----------------
    # 1) si on attend un slot, essayer de le remplir
    waiting_slot = profile.get("__waiting_slot")

    if waiting_slot:
        filled = False

        if waiting_slot == "age":
            age = _extract_age(last_user_text)
            if age is not None:
                profile["age"] = age
                filled = True
                remember_filled_slot(profile, waiting_slot)
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
            yn = _normalize_yes_no(last_user_text)
            profile["celibataire"] = yn if yn else last_user_text
            filled = True
            remember_filled_slot(profile, waiting_slot)

        else:
            clean = sanitize_slot_value(waiting_slot, last_user_text)
            if clean:
                profile[waiting_slot] = clean
                filled = True
                remember_filled_slot(profile, waiting_slot)

        if not filled:
            # relance simple (pas de détour)
            msg_out = await llm_generate("reask_slot", waiting_slot, profile, last_user_text) or fallback_slot_question(waiting_slot, "reask")

            # si "et toi ?" -> répondre Jessie + relancer slot
            if asked and pure_et_toi:
                msg_out = f"{answer_et_toi(detect_et_toi_target_slot(last_user_text) or profile.get('__last_question_slot'))} {msg_out}".strip()

            await human_delay()
            await bot.send_message(user_id, msg_out)
            await _log_staff(bot, topic_id, f"[AUTO][REASK][{waiting_slot}] → {msg_out}")

            _inc_ai_turn(profile)
            _set_question_cooldown(profile, 1)

            upsert_state(
                user_id,
                {
                    "Profile JSON": json.dumps(profile, ensure_ascii=False),
                    "Cooldown Until": (now + datetime.timedelta(seconds=COOLDOWN_SECONDS)).isoformat(),
                },
            )
            return

        # slot rempli -> réaction humaine SANS question
        next_slot = _next_missing_slot(profile)
        profile["__waiting_slot"] = next_slot
        profile["__last_question_slot"] = next_slot or profile.get("__last_question_slot")

        msg_out = await llm_generate("react_only", None, profile, last_user_text) or "Ah ok 😊"
        if asked and pure_et_toi:
            msg_out = f"{answer_et_toi(waiting_slot)} {msg_out}".strip()

        await human_delay()
        await bot.send_message(user_id, msg_out)
        await _log_staff(bot, topic_id, f"[AUTO][FILLED][{waiting_slot}][REACT_ONLY] → {msg_out}")

        _inc_ai_turn(profile)

        upsert_state(
            user_id,
            {
                "Profile JSON": json.dumps(profile, ensure_ascii=False),
                "Cooldown Until": (now + datetime.timedelta(seconds=COOLDOWN_SECONDS)).isoformat(),
            },
        )
        return

    # 2) si pas de waiting_slot: décider si on pose une question (slot manquant)
    missing = _next_missing_slot(profile)
    if missing and _question_allowed(profile) and not _is_greeting(last_user_text):
        profile["__waiting_slot"] = missing
        profile["__last_question_slot"] = missing

        # Question slot = LLM (direct) sauf prénom (déjà acquis ici)
        msg_out = await llm_generate("ask_slot", missing, profile, last_user_text) or fallback_slot_question(missing, "ask")

        # si "et toi ?" -> répondre Jessie + poser la question slot
        if asked and pure_et_toi:
            msg_out = f"{answer_et_toi(detect_et_toi_target_slot(last_user_text) or profile.get('__last_question_slot'))} {msg_out}".strip()

        await human_delay()
        await bot.send_message(user_id, msg_out)
        await _log_staff(bot, topic_id, f"[AUTO][ASK_SLOT][{missing}] → {msg_out}")

        _inc_ai_turn(profile)
        _set_question_cooldown(profile, 1)

        upsert_state(
            user_id,
            {
                "Profile JSON": json.dumps(profile, ensure_ascii=False),
                "Cooldown Until": (now + datetime.timedelta(seconds=COOLDOWN_SECONDS)).isoformat(),
            },
        )
        return

    # 3) sinon: smalltalk
    msg_out = await llm_generate("smalltalk", None, profile, last_user_text) or ("Coucou 😊" if _is_greeting(last_user_text) else "Hmm je vois 😊")
    if asked and pure_et_toi:
        et_toi_slot = profile.get("__last_filled_slot") or profile.get("__last_question_slot")
        msg_out = f"{answer_et_toi(et_toi_slot)} {msg_out}".strip()

    await human_delay()
    await bot.send_message(user_id, msg_out)
    await _log_staff(bot, topic_id, f"[AUTO][SMALLTALK] → {msg_out}")

    _inc_ai_turn(profile)

    upsert_state(
        user_id,
        {
            "Profile JSON": json.dumps(profile, ensure_ascii=False),
            "Cooldown Until": (now + datetime.timedelta(seconds=COOLDOWN_SECONDS)).isoformat(),
        },
    )


# ---------------- MAIN ENTRY ----------------
async def maybe_run_autopilot(message: types.Message, topic_id: int, bot):
    if message.content_type != types.ContentType.TEXT:
        return

    user_id = message.from_user.id
    now = _utcnow()

    state = get_state(user_id)
    if not state:
        upsert_state(
            user_id,
            {
                "Topic ID": str(topic_id),
                "Script ID": (SCRIPT or {}).get("script_id", "script_fr_v1"),
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
    if fields.get("Autopilot") != "ON":
        return

    profile = _safe_json_loads(fields.get("Profile JSON"), {})
    if not isinstance(profile, dict):
        profile = {}

    user_text = (message.text or "").strip()

    # Debounce bundling: on concatène les messages d'une rafale
    bundle = (profile.get("__bundle_text") or "").strip()
    if bundle:
        bundle = bundle + " | " + user_text
    else:
        bundle = user_text
    profile["__bundle_text"] = bundle
    profile["__last_user_text"] = user_text
    profile["__last_user_ts"] = now.isoformat()

    token = str(uuid.uuid4())
    profile["__debounce_token"] = token

    upsert_state(
        user_id,
        {
            "Profile JSON": json.dumps(profile, ensure_ascii=False),
        },
    )

    # démarre une tâche: seule la dernière (token) répondra
    asyncio.create_task(_debounced_autopilot_run(user_id, topic_id, bot, token))
