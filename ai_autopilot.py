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

# Script path fallback (local JSON)
SCRIPT_PATH = os.getenv("AI_SCRIPT_PATH", "script_fr_v1.json")

# ---------------- OpenAI client ----------------
client = None
try:
    from openai import OpenAI
    client = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None
except Exception:
    client = None

# ---------------- Globals ----------------
SCRIPT = None
_last_offer = None


# ---------------- Utilities ----------------
def _utcnow():
    return datetime.datetime.utcnow()


def _safe_json_loads(s, default):
    try:
        if s is None:
            return default
        if isinstance(s, (dict, list)):
            return s
        s = str(s).strip()
        if not s:
            return default
        return json.loads(s)
    except Exception:
        return default


def _parse_airtable_dt(value: str):
    """
    Airtable returns ISO strings like 2025-12-18T20:01:02.123Z
    We store isoformat() without Z sometimes -> handle both.
    """
    if not value:
        return None
    try:
        v = str(value).strip()
        if v.endswith("Z"):
            v = v[:-1]
        return datetime.datetime.fromisoformat(v)
    except Exception:
        return None


def _load_local_script(path: str):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _get_script():
    """
    1) If Airtable Script fetch exists, use it
    2) else fallback local JSON
    """
    if get_script_json:
        try:
            script = get_script_json()
            if script:
                return script
        except Exception:
            pass
    return _load_local_script(SCRIPT_PATH)


SCRIPT = _get_script() or {}
# expected script structure: {"script_id": "...", "steps": [...]}
SCRIPT_STEPS = (SCRIPT or {}).get("steps", [])


def answer_et_toi(slot: str) -> str:
    # simple connector phrase
    options = [
        f"Et toi {slot} ?",
        f"Et toi {slot} alors ?",
        f"Toi {slot} ?",
        f"Et toi du coup {slot} ?",
    ]
    return random.choice(options)


def _clean_text(s: str) -> str:
    if not s:
        return ""
    s = str(s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _extract_user_bundle(profile: dict) -> str:
    """
    You are bundling messages in profile["__bundle_text"] in your handler.
    If not present, use last_user_text.
    """
    bundle = (profile.get("__bundle_text") or "").strip()
    if bundle:
        return bundle
    return (profile.get("__last_user_text") or "").strip()


async def _llm_chat(system: str, user: str) -> str:
    """
    Minimal OpenAI call with timeout.
    """
    if not client:
        return ""

    try:
        loop = asyncio.get_running_loop()

        def _call():
            resp = client.chat.completions.create(
                model=OPENAI_MODEL,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                max_tokens=AI_MAX_OUTPUT_TOKENS,
            )
            return resp.choices[0].message.content or ""

        return await asyncio.wait_for(loop.run_in_executor(None, _call), timeout=LLM_TIMEOUT_SECONDS)
    except Exception:
        return ""


async def _send_once(bot, user_id: int, topic_id: int, profile: dict, text: str) -> bool:
    """
    Send to user, and relay to staff topic if you want in your other module.
    Here we only send to user to keep stable.
    """
    text = _clean_text(text)
    if not text:
        return False
    try:
        await bot.send_message(chat_id=user_id, text=text)
        return True
    except Exception:
        return False


def _score_heat(profile: dict, text: str) -> int:
    """
    Simple heuristic. You probably have your own scoring; keep lightweight.
    """
    t = (text or "").lower()
    score = 0
    keywords = ["photo", "video", "vip", "prix", "combien", "payer", "payment", "acheter", "debloque", "débloque"]
    score += sum(6 for k in keywords if k in t)
    score = max(0, min(SCORE_MAX, score))
    return score


def _should_offer(fields: dict, heat: int) -> bool:
    offers_sent = int(fields.get("Offers Sent") or 0)
    if offers_sent >= 5:
        return False
    if heat >= SCORE_THRESHOLD:
        return True
    return False


# ---------------- Script logic ----------------
def _get_step(step_index: int) -> dict:
    if not SCRIPT_STEPS:
        return {}
    if step_index < 0:
        step_index = 0
    if step_index >= len(SCRIPT_STEPS):
        return {"type": "end"}
    return SCRIPT_STEPS[step_index]


def _run_step(user_id: int, fields: dict, profile: dict) -> Optional[str]:
    """
    Produce a text output based on script steps.
    This is intentionally conservative to avoid breaking your flow.
    """
    step_index = int(fields.get("Step Index") or 0)
    step = _get_step(step_index)
    stype = step.get("type")

    if stype == "say":
        txt = step.get("text") or ""
        return txt

    if stype == "ask":
        # ask a question and store slot hint in profile
        q = step.get("text") or ""
        slot = step.get("slot") or ""
        if slot:
            profile["__pending_slot"] = slot
        return q

    if stype == "wait":
        secs = int(step.get("seconds") or 0)
        if secs > 0:
            now = _utcnow()
            upsert_state(user_id, {"Cooldown Until": (now + datetime.timedelta(seconds=secs)).isoformat()})
        upsert_state(user_id, {"Step Index": step_index + 1})
        return None

    if stype == "end":
        upsert_state(user_id, {"In Script": False, "Step Index": 0})
        return None

    # default: advance
    upsert_state(user_id, {"Step Index": step_index + 1})
    return None


# ---------------- State init ----------------
def ensure_state(user_id: int, topic_id: int):
    # Safety: prevent passing a Message object by mistake
    if not isinstance(user_id, int):
        raise TypeError(f"ensure_state: user_id must be int, got {type(user_id)}")
    if not isinstance(topic_id, int):
        try:
            topic_id = int(topic_id)
        except Exception:
            raise TypeError(f"ensure_state: topic_id must be int, got {type(topic_id)}")

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
                "JustUnlocked": False,          # ✅ checkbox in Airtable
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
    # Safety: prevent passing a Message object by mistake
    if not isinstance(user_id, int):
        raise TypeError(f"maybe_run_autopilot: user_id must be int, got {type(user_id)}")
    if not isinstance(topic_id, int):
        try:
            topic_id = int(topic_id)
        except Exception:
            raise TypeError(f"maybe_run_autopilot: topic_id must be int, got {type(topic_id)}")

    """
    Called on each user message. We debounce bursts and answer once.
    """
    ensure_state(user_id, topic_id)

    # cancel previous task if exists
    old = _pending_tasks.get(user_id)
    if old and not old.done():
        old.cancel()

    token = str(uuid.uuid4())

    # store token
    state = get_state(user_id)
    fields = (state or {}).get("fields", {})
    profile = _safe_json_loads(fields.get("Profile JSON"), {})
    if not isinstance(profile, dict):
        profile = {}

    profile["__debounce_token"] = token
    upsert_state(user_id, {"Profile JSON": json.dumps(profile, ensure_ascii=False)})

    task = asyncio.create_task(_debounced_autopilot_run(user_id, topic_id, bot, token))
    _pending_tasks[user_id] = task


# ---------------- Debounce runner ----------------
async def _debounced_autopilot_run(user_id: int, topic_id: int, bot, token: str):
    if not isinstance(user_id, int):
        raise TypeError(f"_debounced_autopilot_run: user_id must be int, got {type(user_id)}")
    if not isinstance(topic_id, int):
        try:
            topic_id = int(topic_id)
        except Exception:
            raise TypeError(f"_debounced_autopilot_run: topic_id must be int, got {type(topic_id)}")

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

        # if a new message arrived, token changed => abort
        if profile.get("__debounce_token") != token:
            return

        # cooldown global
        now = _utcnow()
        cooldown_str = fields.get("Cooldown Until")
        cd_time = _parse_airtable_dt(cooldown_str) if cooldown_str else None
        if cd_time and now < cd_time:
            return

        last_user_text = _extract_user_bundle(profile)
        if not last_user_text:
            return

        # reset bundle
        profile["__bundle_text"] = ""

        # heat score
        heat = _score_heat(profile, last_user_text)
        upsert_state(user_id, {"Heat": heat})

        # If in script, run next step
        in_script = bool(fields.get("In Script"))
        step_index = int(fields.get("Step Index") or 0)

        msg_out = None

        if in_script:
            msg_out = _run_step(user_id, fields, profile)
            if msg_out:
                upsert_state(user_id, {"Step Index": step_index + 1})
        else:
            # LLM response (general)
            system = (
                "Tu es une modèle IA sexy et naturelle. "
                "Réponds court, simple, humain, sans paraître robot. "
                "Ne pose pas 3 questions d'affilée. "
                "Si l'utilisateur répond et demande 'et toi', réponds d'abord, puis continue doucement."
            )
            user = f"Message client: {last_user_text}\nRéponse:"
            msg_out = await _llm_chat(system, user)

        msg_out = _clean_text(msg_out)

        # If should offer, you will trigger elsewhere (offer_trigger.py)
        # Here we only keep a tiny hint in profile to be used by your other module.
        if _should_offer(fields, heat):
            profile["__should_offer"] = True
        else:
            profile["__should_offer"] = False

        # optional: if slot pending, add "et toi"
        slot = profile.get("__pending_slot")
        if slot and msg_out:
            msg_out = f"{answer_et_toi(slot)} {msg_out}".strip()
            profile["__pending_slot"] = None

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
