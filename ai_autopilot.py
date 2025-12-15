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

# Tu as mis 99999 -> ok, mais on garde la logique au cas où
SAFE_TURNS_LIMIT = int(os.getenv("SAFE_TURNS_LIMIT", "99999"))
COOLDOWN_MINUTES_ON_SAFE_LIMIT = int(os.getenv("COOLDOWN_MINUTES_ON_SAFE_LIMIT", "1"))

BOT_PROFILE = {
    "name": "Jessie",
    "city": "Haute-Savoie, dans les montagnes haha",
    "age": "23",
    "job": "créatrice de contenu et infirmière aussi haha",
    "single": "célibataire malheureusement 😪",
}

# ---- In-memory debounce task manager (anti-double send) ----
_DEBOUNCE_TASKS: dict[int, asyncio.Task] = {}


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


def _norm_msg(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip().lower())


def _is_greeting(text: str) -> bool:
    t = (text or "").strip().lower()
    t = re.sub(r"[^\w\s]", "", t)
    return t in {"salut", "coucou", "hey", "yo", "hello", "cc", "slt", "bonjour"}


def _is_short_greeting_only(text: str) -> bool:
    # "coucou", "salut", "cc", "hey", etc. sans contenu
    t = (text or "").strip().lower()
    t = re.sub(r"[^\w\s]", "", t).strip()
    return _is_greeting(t) and len(t.split()) <= 2


def _looks_like_direct_age_question(text: str) -> bool:
    t = (text or "").lower()
    return ("quel âge" in t) or ("quelle age" in t) or (re.search(r"\btu\s+as\s+(\d{1,2})\s*ans\b", t) is not None)


# ---------------- Slot policy (LE COEUR DU FIX) ----------------
SLOT_ORDER = ["prenom", "ville", "metier", "age", "celibataire"]

# Phase 0 : 2 premiers tours = AUCUNE question
PHASE0_TURNS = 2

# Deadline douce : si on n'a pas demandé de slot depuis X tours -> on force une question slot
SLOT_ASK_DEADLINE_TURNS = 3  # ex: tous les 3 tours max, on pose une question slot (si slots manquants)

# Si un slot a été “ciblé” mais pas rempli -> relance après X tours
SLOT_REASK_AFTER_TURNS = 2


def _next_missing_slot(profile: dict) -> str | None:
    for s in SLOT_ORDER:
        if s not in profile:
            return s
    return None


def _turn_inc(profile: dict):
    profile["__turns_total"] = int(profile.get("__turns_total") or 0) + 1
    profile["__turns_since_slot_ask"] = int(profile.get("__turns_since_slot_ask") or 0) + 1
    profile["__turns_since_last_bot"] = int(profile.get("__turns_since_last_bot") or 0) + 1


def _mark_slot_asked(profile: dict, slot: str):
    profile["__last_question_slot"] = slot
    profile["__last_slot_asked_at_turn"] = int(profile.get("__turns_total") or 0)
    profile["__turns_since_slot_ask"] = 0
    profile["__waiting_slot"] = slot


def _should_ask_slot(profile: dict, last_user_text: str) -> str | None:
    """
    Décide si on DOIT poser une question slot maintenant.
    Retourne le slot à demander, ou None.
    """
    turns_total = int(profile.get("__turns_total") or 0)
    if turns_total < PHASE0_TURNS:
        return None

    # Sur un simple "salut/coucou" très court -> on répond présence, pas question
    if _is_short_greeting_only(last_user_text):
        return None

    missing = _next_missing_slot(profile)
    if not missing:
        return None

    # Si on attend déjà un slot
    waiting = profile.get("__waiting_slot")
    if waiting:
        asked_at = int(profile.get("__last_slot_asked_at_turn") or 0)
        # relance si trop de tours sans remplissage
        if turns_total - asked_at >= SLOT_REASK_AFTER_TURNS:
            return waiting  # reask
        return None

    # Deadline : si ça fait trop longtemps qu’on n’a pas demandé un slot
    if int(profile.get("__turns_since_slot_ask") or 0) >= SLOT_ASK_DEADLINE_TURNS:
        return missing

    # Sinon on laisse vivre
    return None


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
        "ville": "sa ville / d’où il vient",
        "age": "son âge",
        "metier": "ce qu’il fait dans la vie",
        "celibataire": "son statut (libre/en couple)",
    }.get(slot, slot)


async def llm_generate(intent: str, slot: str | None, profile: dict, last_user_text: str) -> str | None:
    """
    intent:
      - phase0_hello: entrée douce sur salut/coucou, SANS question
      - ask_slot: pose UNE question directe pour obtenir le slot
      - reask_slot: relance simple (1 fois) pour obtenir le slot
      - react_only: réponse humaine SANS question (après slot rempli)
      - smalltalk: réponse humaine libre (peut contenir une question max)
    """
    if not client:
        return None

    user_profile = _profile_public(profile)
    have = ", ".join([f"{k}={v}" for k, v in user_profile.items()]) or "rien pour l’instant"
    target = _slot_label(slot) if slot else "rien"

    turns_total = int(profile.get("__turns_total") or 0)

    system = (
        "Tu t’appelles Jessie. Tu parles comme une vraie femme sur Telegram: naturelle, calme, un peu taquine. "
        "Tu dois être crédible et simple (jamais robot). "
        "Règles STRICTES: 1 phrase (parfois 2 max), pas de listes, pas de paragraphe, 0 à 1 emoji. "
        "Tu ne répètes jamais la même phrase deux fois de suite. "
        "Tu évites les mots vides type 'je vois', 'd’accord' quand ça n’apporte rien. "
        "Tu n’utilises pas le prénom du client à chaque message: максимум 1 fois tous les 6 messages, et seulement si ça sonne naturel. "
        "Interdit: mentionner IA/bot/script/API, paiement, prix. "
        "Tu ne fais pas d’affirmations inventées sur lui. Si tu ne sais pas, tu demandes simplement."
    )

    if intent == "phase0_hello":
        instruction = (
            "Le client vient juste de dire salut/coucou. "
            "Fais une entrée douce, courte, chaleureuse, SANS question. "
            "Exemple de vibe: 'Coucou toi 🤭' / 'Hey toi 😌' (mais ne copie pas à l’identique)."
        )
    elif intent == "ask_slot":
        instruction = (
            f"Tu dois obtenir {target}. "
            f"Tu sais déjà: {have}. "
            "Fais une réponse/presence courte + UNE question directe et naturelle (pas d’enrobage suspect)."
        )
    elif intent == "reask_slot":
        instruction = (
            f"Tu attends {target} mais il n’a pas répondu clairement. "
            f"Tu sais déjà: {have}. "
            "Relance UNE fois, simplement, en une seule phrase."
        )
    elif intent == "react_only":
        instruction = (
            "Réponds de façon humaine à son dernier message SANS poser de question. "
            f"Tu sais déjà: {have}."
        )
    else:
        # smalltalk
        instruction = (
            f"Réponds naturellement. Tu peux ajouter UNE question max si c’est vraiment naturel. "
            f"Tu sais déjà: {have}. "
            f"Contexte: tour={turns_total}."
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
            return "Tu viens d’où exactement ? 😊"
        if slot == "metier":
            return "Tu fais quoi dans la vie ? 😊"
        if slot == "age":
            return "Tu as quel âge ? 😊"
        if slot == "celibataire":
            return "T’es plutôt libre ou en couple ? 😏"
        return "Dis-m’en un peu plus 😊"

    if slot == "prenom":
        return "Au fait, je t’ai même pas demandé ton prénom 😊"
    if slot == "ville":
        return "Tu viens d’où ? 😊"
    if slot == "metier":
        return "Tu fais quoi dans la vie ? 😊"
    if slot == "age":
        return "Tu as quel âge ? 😊"
    if slot == "celibataire":
        return "T’es célibataire ou plutôt en couple ? 😏"
    return "Dis-m’en un peu plus 😊"


def _variant_if_duplicate(text: str) -> str:
    # petite variation si anti-duplicate bloque
    variants = ["😌", "🤭", "😊", ""]
    v = random.choice(variants)
    t = (text or "").strip()
    if not t:
        return t
    if v and not t.endswith(v):
        return f"{t} {v}".strip()
    return t


async def _send_once(bot, user_id: int, topic_id: int, profile: dict, text: str):
    """
    Envoi protégé anti-doublon (même message) + fallback variante si doublon.
    """
    msg = (text or "").strip()
    if not msg:
        return False

    last_bot = _norm_msg(profile.get("__last_bot_text", ""))

    # anti-répétition : si identique -> on tente une variante
    if _norm_msg(msg) == last_bot:
        msg2 = _variant_if_duplicate(msg)
        if _norm_msg(msg2) == last_bot:
            # dernier recours : message court différent
            msg2 = random.choice(["Haha 😌", "Ok 😌", "Mmh 😌", "Je vois 😌"]).strip()
        msg = msg2

    await human_delay()
    await bot.send_message(user_id, msg)

    profile["__last_bot_text"] = msg
    profile["__turns_since_last_bot"] = 0
    await _log_staff(bot, topic_id, f"[AUTO] → {msg}")
    return True


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

        # incrément tour (IMPORTANT : fait ici, pas dans maybe_run_autopilot)
        _turn_inc(profile)

        profile.setdefault("safe_turns", 0)
        profile.setdefault("phase", "ACQ")
        profile.setdefault("palier", 1)

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
                    "Cooldown Until": (now + datetime.timedelta(seconds=COOLDOWN_SECONDS)).isoformat() if sent else fields.get("Cooldown Until"),
                },
            )
            return

        # 1) Si le client demande "et toi ?" -> répondre UNIQUEMENT au bon slot (et pas au hasard)
        explicit_et_toi_slot = None
        if asked_et_toi:
            explicit_et_toi_slot = detect_et_toi_target_slot(last_user_text)
            if not explicit_et_toi_slot:
                # si "et toi ?" sans précision -> on répond sur le dernier sujet de Jessie si connu
                explicit_et_toi_slot = profile.get("__last_question_slot") or profile.get("__last_filled_slot")

        # 2) Remplissage slot si on attend une réponse
        waiting_slot = profile.get("__waiting_slot")
        if waiting_slot:
            filled = False

            if waiting_slot == "age":
                age = _extract_age(last_user_text)
                if age is not None:
                    profile["age"] = age
                    filled = True
                    remember_filled_slot(profile, waiting_slot)
                    profile["__waiting_slot"] = None  # on arrête d'attendre

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
                profile["__waiting_slot"] = None

            else:
                clean = sanitize_slot_value(waiting_slot, last_user_text)
                if clean:
                    profile[waiting_slot] = clean
                    filled = True
                    remember_filled_slot(profile, waiting_slot)
                    profile["__waiting_slot"] = None

            if not filled:
                # relance simple seulement si la policy le décide
                slot_to_reask = _should_ask_slot(profile, last_user_text)
                if slot_to_reask == waiting_slot:
                    _mark_slot_asked(profile, waiting_slot)
                    msg_out = await llm_generate("reask_slot", waiting_slot, profile, last_user_text) or fallback_slot_question(waiting_slot, "reask")
                    if asked_et_toi and pure_et_toi and explicit_et_toi_slot:
                        msg_out = f"{answer_et_toi(explicit_et_toi_slot)} {msg_out}".strip()
                    sent = await _send_once(bot, user_id, topic_id, profile, msg_out)
                    upsert_state(
                        user_id,
                        {
                            "Profile JSON": json.dumps(profile, ensure_ascii=False),
                            "Cooldown Until": (now + datetime.timedelta(seconds=COOLDOWN_SECONDS)).isoformat() if sent else fields.get("Cooldown Until"),
                        },
                    )
                    return
                # sinon on continue smalltalk sans relancer le slot
                profile["__waiting_slot"] = waiting_slot

            else:
                # slot rempli => réponse humaine SANS question
                msg_out = await llm_generate("react_only", None, profile, last_user_text) or "Ah ok 😌"
                if asked_et_toi and pure_et_toi and explicit_et_toi_slot:
                    msg_out = f"{answer_et_toi(explicit_et_toi_slot)} {msg_out}".strip()
                sent = await _send_once(bot, user_id, topic_id, profile, msg_out)
                upsert_state(
                    user_id,
                    {
                        "Profile JSON": json.dumps(profile, ensure_ascii=False),
                        "Cooldown Until": (now + datetime.timedelta(seconds=COOLDOWN_SECONDS)).isoformat() if sent else fields.get("Cooldown Until"),
                    },
                )
                return

        # 3) Si on n'attend pas un slot, on décide si on DOIT en demander un maintenant
        slot_to_ask = _should_ask_slot(profile, last_user_text)
        if slot_to_ask:
            _mark_slot_asked(profile, slot_to_ask)
            msg_out = await llm_generate("ask_slot", slot_to_ask, profile, last_user_text) or fallback_slot_question(slot_to_ask, "ask")
            if asked_et_toi and pure_et_toi and explicit_et_toi_slot:
                msg_out = f"{answer_et_toi(explicit_et_toi_slot)} {msg_out}".strip()
            sent = await _send_once(bot, user_id, topic_id, profile, msg_out)
            upsert_state(
                user_id,
                {
                    "Profile JSON": json.dumps(profile, ensure_ascii=False),
                    "Cooldown Until": (now + datetime.timedelta(seconds=COOLDOWN_SECONDS)).isoformat() if sent else fields.get("Cooldown Until"),
                },
            )
            return

        # 4) Sinon: smalltalk (mais sans sortir des infos BOT_PROFILE hors contexte)
        msg_out = await llm_generate("smalltalk", None, profile, last_user_text) or "Coucou 😌"

        # Répondre à "et toi ?" UNIQUEMENT si la phrase contient vraiment "et toi"
        if asked_et_toi and explicit_et_toi_slot:
            msg_out = f"{answer_et_toi(explicit_et_toi_slot)} {msg_out}".strip()

        sent = await _send_once(bot, user_id, topic_id, profile, msg_out)
        upsert_state(
            user_id,
            {
                "Profile JSON": json.dumps(profile, ensure_ascii=False),
                "Cooldown Until": (now + datetime.timedelta(seconds=COOLDOWN_SECONDS)).isoformat() if sent else fields.get("Cooldown Until"),
            },
        )

    except Exception as e:
        # IMPORTANT : si un bug arrive, ça ne doit jamais "bloquer" en silence
        print(f"❌ [AI] autopilot error user_id={user_id}: {e}")


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

    # ✅ annule la tâche précédente -> une seule réponse possible
    old = _DEBOUNCE_TASKS.get(user_id)
    if old and not old.done():
        old.cancel()

    task = asyncio.create_task(_debounced_autopilot_run(user_id, topic_id, bot, token))
    _DEBOUNCE_TASKS[user_id] = task
