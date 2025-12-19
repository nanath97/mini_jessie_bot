import os
import json
import random
import re
import datetime
import asyncio
import uuid
from ai_state_store import get_state, upsert_state
from aiogram import types

# Script fetch (Airtable ScriptOFM)
try:
    from ai_state_store import get_script_json  # patched ai_state_store
except Exception:
    get_script_json = None

# Offer trigger (NovaPulse offers)
try:
    from offer_trigger import trigger_offer
except Exception:
    trigger_offer = None

# OpenAI SDK (official)
from openai import OpenAI


# ---------------- LLM CONFIG ----------------
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")  # ok for fast chatting
AI_MAX_OUTPUT_TOKENS = int(os.getenv("AI_MAX_OUTPUT_TOKENS", "80"))
LLM_TIMEOUT_SECONDS = int(os.getenv("LLM_TIMEOUT_SECONDS", "12"))

# ---------------- SALES / HEAT CONFIG ----------------
SCORE_THRESHOLD = int(os.getenv("AI_SCORE_THRESHOLD", "45"))  # confirmed: 45
SCORE_MAX = int(os.getenv("AI_SCORE_MAX", "100"))


# ---------------- BOT / SCRIPT CONFIG ----------------
COOLDOWN_SECONDS = int(os.getenv("COOLDOWN_SECONDS", "8"))
DEBOUNCE_SECONDS = float(os.getenv("DEBOUNCE_SECONDS", "1.2"))
SCRIPT_PATH = os.getenv("AI_SCRIPT_PATH", "script_fr_v1.json")

# Tu as mis 99999 -> ok, mais on garde la logique au cas où
SAFE_TURNS_LIMIT = int(os.getenv("SAFE_TURNS_LIMIT", "8"))
COOLDOWN_MINUTES_ON_SAFE_LIMIT = int(os.getenv("COOLDOWN_MINUTES_ON_SAFE_LIMIT", "30"))

PHASE0_TURNS = int(os.getenv("PHASE0_TURNS", "1"))

# Slots / policy
SLOT_ASK_DEADLINE_TURNS = int(os.getenv("SLOT_ASK_DEADLINE_TURNS", "5"))


# ---------------- OpenAI client ----------------
client = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None


# ---------------- Time helpers ----------------
def _utcnow():
    return datetime.datetime.utcnow().replace(tzinfo=datetime.timezone.utc)


def _parse_airtable_dt(s: str):
    if not s:
        return None
    try:
        # accepts "2025-12-18T12:34:56.000Z" or isoformat
        if s.endswith("Z"):
            s = s.replace("Z", "+00:00")
        return datetime.datetime.fromisoformat(s)
    except Exception:
        return None


# ---------------- JSON helpers ----------------
def _safe_json_loads(s: str, default):
    try:
        obj = json.loads(s) if s else default
        return obj
    except Exception:
        return default


# ---------------- Text helpers ----------------
def _norm_msg(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip().lower())


def _is_greeting(text: str) -> bool:
    t = (text or "").strip().lower()
    t = re.sub(r"[^\w\s]", "", t)
    return t in {"salut", "coucou", "hey", "yo", "hello", "cc", "slt", "bonjour"}


def _is_short_greeting_only(text: str) -> bool:
    t = (text or "").strip().lower()
    t = re.sub(r"[^\w\s]", "", t).strip()
    return t in {"salut", "coucou", "hey", "yo", "hello", "cc", "slt", "bonjour"}


def _extract_age(text: str):
    if not text:
        return None
    m = re.search(r"\b(\d{1,2})\b", text)
    if not m:
        return None
    try:
        age = int(m.group(1))
        if 0 < age < 120:
            return age
    except Exception:
        return None
    return None


def _normalize_yes_no(text: str):
    if not text:
        return None
    t = _norm_msg(text)
    if t in {"oui", "ouais", "yes", "yep", "ok", "daccord", "d'accord"}:
        return "oui"
    if t in {"non", "no", "nope", "nan"}:
        return "non"
    return None


def sanitize_slot_value(slot: str, text: str) -> str:
    # minimal sanitization
    v = (text or "").strip()
    v = re.sub(r"\s+", " ", v)
    return v[:80]


def remember_filled_slot(profile: dict, slot: str):
    profile["__last_filled_slot"] = slot


def _mark_slot_asked(profile: dict, slot: str):
    asked = profile.get("__asked_slots") or {}
    if not isinstance(asked, dict):
        asked = {}
    asked[slot] = int(profile.get("__turns_total") or 0)
    profile["__asked_slots"] = asked
    profile["__last_question_slot"] = slot


def _turn_inc(profile: dict):
    profile["__turns_total"] = int(profile.get("__turns_total") or 0) + 1


def is_et_toi(text: str) -> bool:
    t = (text or "").strip().lower()
    return ("et toi" in t) or ("toi ?" in t) or ("toi aussi" in t)


def is_pure_et_toi(text: str) -> bool:
    t = (text or "").strip().lower()
    t = re.sub(r"[^\w\s?]", "", t).strip()
    return t in {"et toi", "et toi?", "toi ?", "toi?"}


def detect_et_toi_target_slot(text: str):
    t = (text or "").lower()
    if "age" in t or "ans" in t:
        return "age"
    if "tu fais quoi" in t or "job" in t or "travail" in t:
        return "job"
    if "t'habite" in t or "tu viens d'où" in t or "ville" in t:
        return "city"
    if "célib" in t or "en couple" in t:
        return "celibataire"
    if "ton prénom" in t or "comment tu t'appelles" in t:
        return "name"
    return None


def answer_et_toi(slot: str) -> str:
    # minimal persona (Jessie, 27)
    persona = {
        "name": "Jessie",
        "age": "27",
        "job": "créatrice de contenu",
        "city": "Haute-Savoie",
        "celibataire": "célibataire",
    }
    if slot == "name":
        return f"Moi c’est {persona['name']} 😊"
    if slot == "age":
        return f"J’ai {persona['age']} ans 😌"
    if slot == "job":
        return f"Je suis {persona['job']} hehe"
    if slot == "city":
        return f"Je suis vers {persona['city']} 😄"
    if slot == "celibataire":
        return f"Je suis {persona['celibataire']}… et toi ?"
    return "Moi ? 😌"


# ---------------- LLM message generation ----------------
async def llm_generate(mode: str, slot: str, profile: dict, last_user_text: str) -> str:
    """
    Lightweight LLM call. Keep short replies, natural.
    """
    if not client:
        return None

    system = (
        "Tu es Jessie (27 ans). Tu écris comme une vraie humaine, simple, naturelle. "
        "Tu réponds à la question du client avant de relancer. "
        "Tu évites d'enchaîner des questions mécaniques. "
        "Réponses courtes (1-2 phrases)."
    )

    user = f"Mode={mode}\nSlot={slot}\nProfil={json.dumps(profile, ensure_ascii=False)}\nClient={last_user_text}\n"
    try:
        resp = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            max_tokens=AI_MAX_OUTPUT_TOKENS,
            timeout=LLM_TIMEOUT_SECONDS,
        )
        out = resp.choices[0].message.content.strip()
        return out[:300]
    except Exception as e:
        print(f"[AI] LLM error: {e}")
        return None


# ---------------- Script loader (local fallback) ----------------
def _load_script():
    with open(SCRIPT_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


try:
    SCRIPT = _load_script()
except Exception as e:
    print(f"❌ [AI] Impossible de charger le script {SCRIPT_PATH}: {e}")
    SCRIPT = None


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
        r"\bcombien\b", r"\bprix\b", r"\bpay\b", r"\bpayer\b", r"\bachète\b", r"\acheter\b",
        r"\blien\b", r"\bcarte\b", r"\bpaypal\b", r"\bstripe\b",
        r"\bvip\b",
    ]
    return any(re.search(p, t) for p in patterns)


# ---------------- Heat / score helpers ----------------
def _clamp(v: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, int(v)))


def _score_delta(text: str, desire: bool, buyer: bool) -> int:
    """
    Simple, explainable scoring:
    - buyer signal -> big jump
    - desire signal -> medium jump
    - longer engaged text -> small bonus
    - otherwise slight decay
    """
    t = (text or "").strip()
    delta = 0
    if buyer:
        delta += 20
    if desire:
        delta += 10
    if len(t) >= 40:
        delta += 3
    elif len(t) >= 15:
        delta += 1
    if delta == 0:
        delta = -1
    return delta


def _parse_json_safe(raw: str) -> dict:
    obj = _safe_json_loads(raw, {})
    return obj if isinstance(obj, dict) else {}


def _get_script_obj(fields: dict) -> dict:
    """Get script JSON from Airtable if available, else fallback to local SCRIPT."""
    script_id = str(fields.get("Script ID") or (SCRIPT or {}).get("script_id", "script_fr_v1"))
    if get_script_json:
        raw = get_script_json(script_id)
        obj = _parse_json_safe(raw)
        if obj:
            return obj
    return SCRIPT or {}


def _pick_presex_message(script_obj: dict) -> str:
    arr = script_obj.get("presex") or script_obj.get("presex_messages") or []
    if isinstance(arr, list) and arr:
        item = random.choice(arr)
        if isinstance(item, dict):
            return str(item.get("text") or "").strip()
        return str(item).strip()
    # fallback
    return "Tu sais quoi… j’ai envie qu’on passe à un truc un peu plus fun 😏"


def _get_steps(script_obj: dict) -> list:
    steps = script_obj.get("steps") or []
    return steps if isinstance(steps, list) else []


# ---------------- Sending helper (topic-safe) ----------------
async def _send_once(bot, user_id: int, topic_id: int, profile: dict, text: str) -> bool:
    """
    Sends to user DM (not staff topic). Keep as your current behavior:
    user receives messages, staff topic is for staff logs elsewhere.
    """
    try:
        await bot.send_message(chat_id=user_id, text=text)
        return True
    except Exception as e:
        print(f"[AI] send failed user_id={user_id}: {e}")
        return False


async def _run_script_step(bot, user_id: int, topic_id: int, fields: dict, profile: dict) -> bool:
    """
    Executes ONE script step per user message (Option A).
    Uses Airtable field 'Step Index' and boolean 'In Script'.
    """
    script_obj = _get_script_obj(fields)
    steps = _get_steps(script_obj)

    if not steps:
        upsert_state(user_id, {"In Script": False})
        return False

    step_index = int(fields.get("Step Index") or 0)
    if step_index < 0:
        step_index = 0

    if step_index >= len(steps):
        upsert_state(user_id, {"In Script": False, "Step Index": 0})
        return False

    step = steps[step_index]
    if not isinstance(step, dict):
        upsert_state(user_id, {"Step Index": step_index + 1})
        return True

    stype = (step.get("type") or "").lower()

    if stype == "text":
        txt = str(step.get("text") or "").strip()
        if txt:
            sent = await _send_once(bot, user_id, topic_id, profile, txt)
            if sent:
                upsert_state(user_id, {"Step Index": step_index + 1})
                return True
        upsert_state(user_id, {"Step Index": step_index + 1})
        return True

    if stype == "media_push":
        kind = (step.get("media_kind") or "photo").lower()
        media_ref = str(step.get("media_ref") or "").strip()
        caption = str(step.get("caption") or "").strip() or None
        try:
            if kind == "photo":
                await bot.send_photo(chat_id=user_id, photo=media_ref, caption=caption)
            elif kind == "video":
                await bot.send_video(chat_id=user_id, video=media_ref, caption=caption)
            else:
                await bot.send_document(chat_id=user_id, document=media_ref, caption=caption)
        except Exception as e:
            print(f"[AI_SCRIPT] media_push failed user_id={user_id}: {e}")
        upsert_state(user_id, {"Step Index": step_index + 1})
        return True

    if stype == "offer":
        offer_key = str(step.get("offer_key") or "").strip()
        txt = str(step.get("text") or "").strip()

        if txt:
            await _send_once(bot, user_id, topic_id, profile, txt)

        if offer_key and trigger_offer:
            try:
                await trigger_offer(bot, user_id, offer_key, origin="AI_SCRIPT")
            except Exception as e:
                print(f"[AI_SCRIPT] trigger_offer failed user_id={user_id}: {e}")

        upsert_state(user_id, {"Step Index": step_index + 1})
        return True

    if stype == "wait":
        secs = int(step.get("seconds") or 0)
        if secs > 0:
            now = _utcnow()
            upsert_state(user_id, {"Cooldown Until": (now + datetime.timedelta(seconds=secs)).isoformat()})
        upsert_state(user_id, {"Step Index": step_index + 1})
        return True

    if stype == "end":
        upsert_state(user_id, {"In Script": False, "Step Index": 0})
        return True

    upsert_state(user_id, {"Step Index": step_index + 1})
    return True


# ---------------- State init ----------------
def ensure_state(user_id: int, topic_id: int):
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
                "JustUnlocked": False,
                "Offers Sent": 0,
                "In Script": False,
                "Pending Fillers JSON": "[]",
                "Autopilot": "OFF",
                "Cooldown Until": None,
            },
        )
        return


# ---------------- Debounce scheduler ----------------
_pending_tasks = {}  # user_id -> asyncio.Task


async def maybe_run_autopilot(user_id: int, topic_id: int, bot):
    """
    Called on each user message. We debounce bursts and answer once.
    """
    ensure_state(user_id, topic_id)

    # cancel previous task if exists
    old = _pending_tasks.get(user_id)
    if old and not old.done():
        old.cancel()

    token = str(uuid.uuid4())
    # store token + bundle
    state = get_state(user_id)
    fields = (state or {}).get("fields", {})
    profile = _safe_json_loads(fields.get("Profile JSON"), {})
    if not isinstance(profile, dict):
        profile = {}

    # bundle messages
    txt = (profile.get("__bundle_text") or "")
    last_text = (profile.get("__last_user_text") or "")
    profile["__debounce_token"] = token

    # caller should set __last_user_text + __bundle_text outside or in your handler
    # we keep existing behavior: you already store it elsewhere
    upsert_state(user_id, {"Profile JSON": json.dumps(profile, ensure_ascii=False)})

    task = asyncio.create_task(_debounced_autopilot_run(user_id, topic_id, bot, token))
    _pending_tasks[user_id] = task


# ---------------- Debounce runner ----------------
async def _debounced_autopilot_run(user_id: int, topic_id: int, bot, token: str):
    """
    Attend la fin d'une rafale de messages, puis répond UNE seule fois.
    """
    try:
        await asyncio.sleep(DEBOUNCE_SECONDS)
    except asyncio.CancelledError:
        return

    try:
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

        bundle = profile.get("__bundle_text", "")
        last_user_text = (bundle or profile.get("__last_user_text") or "").strip()
        if not last_user_text:
            return

        # nettoyage bundle
        profile["__bundle_text"] = ""

        # incrément tour
        _turn_inc(profile)

        profile.setdefault("safe_turns", 0)
        profile.setdefault("phase", "ACQ")
        profile.setdefault("palier", 1)

        desire_signal = detect_desire_signal(last_user_text)
        buyer_signal = detect_buyer_signal(last_user_text)

        # --- HEAT / UNLOCK ---
        prev_score = int(fields.get("Heat") or 0)
        offers_sent = int(fields.get("Offers Sent") or 0)
        just_unlocked = bool(fields.get("JustUnlocked") or False)
        in_script = bool(fields.get("In Script") or False)

        delta = _score_delta(last_user_text, desire_signal, buyer_signal)
        score = _clamp(prev_score + delta, 0, SCORE_MAX)

        # Cross threshold => unlock once
        if (not just_unlocked) and prev_score < SCORE_THRESHOLD and score >= SCORE_THRESHOLD:
            just_unlocked = True

        # If just unlocked: send ONE presex transition from script, then activate script for next user msg
        if just_unlocked:
            script_obj = _get_script_obj(fields)
            presex_msg = _pick_presex_message(script_obj)
            sent = await _send_once(bot, user_id, topic_id, profile, presex_msg)

            upsert_state(
                user_id,
                {
                    "Profile JSON": json.dumps(profile, ensure_ascii=False),
                    "JustUnlocked": False,
                    "Heat": score,
                    "In Script": True,
                    "Step Index": 0,
                    "Updated At": datetime.datetime.utcnow().isoformat(),
                    "Cooldown Until": (now + datetime.timedelta(seconds=COOLDOWN_SECONDS)).isoformat()
                    if sent else fields.get("Cooldown Until"),
                },
            )
            return

        # Persist score on normal path
        upsert_state(
            user_id,
            {
                "Heat": score,
                "JustUnlocked": False,
                "Updated At": datetime.datetime.utcnow().isoformat(),
            },
        )

        # Reset / increment "safe turns"
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

        # --- SCRIPT RUNNER (Option A) ---
        if bool(fields.get("In Script") or False):
            ran = await _run_script_step(bot, user_id, topic_id, fields, profile)
            if ran:
                upsert_state(user_id, {"Profile JSON": json.dumps(profile, ensure_ascii=False)})
                return

        asked_et_toi = is_et_toi(last_user_text)
        pure_et_toi = is_pure_et_toi(last_user_text)

        # Phase 0: sur salut/coucou -> entrée douce, sans question
        if _is_short_greeting_only(last_user_text) and int(profile.get("__turns_total") or 0) <= PHASE0_TURNS:
            msg_out = await llm_generate("phase0_hello", None, profile, last_user_text) or "Coucou toi 🤭"
            sent = await _send_once(bot, user_id, topic_id, profile, msg_out)
            upsert_state(
                user_id,
                {
                    "Profile JSON": json.dumps(profile, ensure_ascii=False),
                    "Cooldown Until": (now + datetime.timedelta(seconds=COOLDOWN_SECONDS)).isoformat()
                    if sent else fields.get("Cooldown Until"),
                },
            )
            return

        # (Ton reste de logique acquisition/slots peut rester ici; version courte fallback)
        msg_out = await llm_generate("smalltalk", None, profile, last_user_text) or "Mhmm 😌"
        if asked_et_toi:
            slot = detect_et_toi_target_slot(last_user_text) or profile.get("__last_question_slot") or profile.get("__last_filled_slot")
            if slot:
                msg_out = f"{answer_et_toi(slot)} {msg_out}".strip()

        sent = await _send_once(bot, user_id, topic_id, profile, msg_out)
        upsert_state(
            user_id,
            {
                "Profile JSON": json.dumps(profile, ensure_ascii=False),
                "Cooldown Until": (now + datetime.timedelta(seconds=COOLDOWN_SECONDS)).isoformat()
                if sent else fields.get("Cooldown Until"),
            },
        )

    except Exception as e:
        print(f"❌ [AI] autopilot error user_id={user_id}: {e}")
