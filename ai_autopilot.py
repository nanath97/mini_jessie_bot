import os
import json
import random
import re
import datetime
import asyncio
from ai_state_store import get_state, upsert_state
from aiogram import types

# OpenAI SDK (official)
from openai import OpenAI


# ---------------- LLM CONFIG ----------------
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
AI_MODEL = os.getenv("AI_MODEL", "gpt-4.1")  # stable + bon en dialogue
AI_TONE = os.getenv("AI_TONE", "fr")         # "fr" or "pt" etc.

# Limit cost + avoid long rambles
LLM_MAX_OUTPUT_TOKENS = int(os.getenv("LLM_MAX_OUTPUT_TOKENS", "80"))
LLM_TIMEOUT_SECONDS = int(os.getenv("LLM_TIMEOUT_SECONDS", "20"))

client = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None


async def human_delay(min_s=6, max_s=15):
    await asyncio.sleep(random.uniform(min_s, max_s))


# ---------------- CONFIG ----------------
STAFF_GROUP_ID = int(os.getenv("STAFF_GROUP_ID", "0"))
COOLDOWN_SECONDS = 8

SCRIPT_PATH = os.getenv("AI_SCRIPT_PATH", "script_fr_v1.json")

SAFE_TURNS_LIMIT = 15
COOLDOWN_MINUTES_ON_SAFE_LIMIT = 30

SHIFT_MIN_SECONDS_BETWEEN = 90
OFFER_COOLDOWN_SECONDS = 180
OFFER_MIN_PALIER = 4

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

SHIFT_VIBE_MESSAGES = [
    "Ok je vois 😌",
    "Haha j’avoue 🤭",
    "T’es marrant toi 😏",
    "J’aime bien ton énergie 😌",
    "Mmh intéressant… 😏",
    "Ok… ça devient intriguant 😌",
]

SHIFT_CURIOSITY_TEMPLATES = [
    "Ok 😌 et toi t’es plutôt {topic_a} ou {topic_b} ?",
    "Haha 😏 dis-moi, t’es plus {topic_a} ou {topic_b} ?",
    "Je vois 😊 t’es team {topic_a} ou team {topic_b} ?",
]

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


def should_offer_tier(profile: dict, buyer_signal: bool, desire_signal: bool) -> bool:
    palier = int(profile.get("palier") or 1)
    return palier >= OFFER_MIN_PALIER and buyer_signal


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
    """Only keep safe user fields we want the model to see."""
    keep = {}
    for k, v in profile.items():
        if k.startswith("__"):
            continue
        # only store known slots + small helpers
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
      - ask_slot: poser une question naturelle pour obtenir le slot
      - reask_slot: relance douce si la réponse n’a pas rempli le slot
      - smalltalk: réaction naturelle + mini rebond (sans chercher un slot)
    """
    if not client:
        return None

    user_profile = _profile_public(profile)
    have = ", ".join([f"{k}={v}" for k, v in user_profile.items()]) or "rien pour l’instant"
    target = _slot_label(slot) if slot else "rien"

    # IMPORTANT: V1 acquisition only. We keep it safe: no explicit sexual content generation here.

    system = (
    "Tu es Jessie, une femme séduisante, naturelle et à l’aise dans la discussion. "
    "Tu parles comme une vraie personne, jamais comme un robot. "
    "Objectif principal: créer une connexion agréable, fluide, féminine, qui donne envie de continuer à parler. "
    "Objectif secondaire, discret mais obligatoire: apprendre progressivement son prénom, son âge, sa ville/environnement, "
    "son métier/activité, et son rythme de vie. "
    "Ces infos ne doivent jamais être demandées comme un questionnaire. "
    "Règles: au maximum une question personnelle par message; parfois aucune question pendant plusieurs messages; "
    "réaction émotionnelle d’abord, curiosité ensuite; rebondis sur un mot/émotion; si une info manque, reviens plus tard sous un autre angle; "
    "n’insiste jamais frontalement. "
    "Style: français simple, chat, 1 phrase courte (max ~18 mots), pas de listes, pas de paragraphe, 0 ou 2 emojis max. "
    "Interdit: mentionner slot/script/IA/bot/API; parler de paiement/offre/prix. "
    "Stade actuel: uniquement connexion et découverte, pas de sexualisation explicite."
)

    if intent == "ask_slot":
        instruction = (
            f"Tu veux obtenir {target} de manière fluide. "
            f"Tu sais déjà: {have}. "
            "Formule une phrase naturelle qui rebondit sur ce qu’il vient de dire et obtient l’info."
        )
    elif intent == "reask_slot":
        instruction = (
            f"Tu attends {target} mais il n’a pas répondu clairement. "
            f"Tu sais déjà: {have}. "
            "Fais une relance douce et naturelle (pas insistante), en une seule phrase."
        )
    else:
        instruction = (
            f"Répond naturellement à son dernier message et ajoute un mini rebond convivial (sans chercher une info). "
            f"Tu sais déjà: {have}."
        )

    # Use Responses API input as simple string (enough for V1)
    prompt = (
        f"{instruction}\n\n"
        f"Dernier message du client: {last_user_text}\n"
        f"Réponds maintenant:"
    )

    try:
        # Run blocking SDK call in thread to avoid blocking event loop
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
        # hard clean
        text = re.sub(r"\s+", " ", text).strip()
        # safety guard: avoid empty
        return text if text else None
    except Exception as e:
        print(f"❌ [LLM] generation failed: {e}")
        return None


def fallback_slot_question(slot: str, profile: dict, mode: str = "ask") -> str:
    """Fallback ultra simple si LLM indispo."""
    if mode == "reask":
        if slot == "prenom":
            return "Au fait, je peux savoir ton prénom ? 😊"
        if slot == "ville":
            return "Tu viens d’où exactement ? 😌"
        if slot == "age":
            return "Tu as quel âge ? 😌"
        if slot == "metier":
            return "Tu fais quoi comme boulot ? 😊"
        if slot == "celibataire":
            return "Et toi t’es plutôt libre ou en couple ? 😏"
        return "Dis-m’en un peu plus 😊"

    # ask
    if slot == "prenom":
        return "Tu t’appelles comment ? 😌"
    if slot == "ville":
        return "Tu es de quelle ville ? 😊"
    if slot == "age":
        return "Tu as quel âge ? 😌"
    if slot == "metier":
        return "Tu fais quoi dans la vie ? 😊"
    if slot == "celibataire":
        return "T’es célibataire ou déjà pris ? 😏"
    return "Dis-m’en un peu plus 😊"


# ---------------- MAIN ----------------
async def maybe_run_autopilot(message: types.Message, topic_id: int, bot):
    if message.content_type != types.ContentType.TEXT:
        return
    if not SCRIPT or "steps" not in SCRIPT:
        # Script is now fallback-only, but keep guard
        pass

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

    cooldown_str = fields.get("Cooldown Until")
    cd_time = _parse_airtable_dt(cooldown_str) if cooldown_str else None
    if cd_time and now < cd_time:
        return

    profile = _safe_json_loads(fields.get("Profile JSON"), {})
    if not isinstance(profile, dict):
        profile = {}

    profile.setdefault("safe_turns", 0)
    profile.setdefault("phase", "ACQ")   # acquisition only V1
    profile.setdefault("palier", 1)
    # Init slot seulement au tout début (évite de re-demander plus tard)
    if "__waiting_slot" not in profile and "prenom" not in profile:
        profile["__waiting_slot"] = "prenom"
        profile["__last_question_slot"] = "prenom"



    user_text = (message.text or "").strip()

    asked = is_et_toi(user_text)
    pure_et_toi = is_pure_et_toi(user_text)
    waiting_slot = profile.get("__waiting_slot")

    desire_signal = detect_desire_signal(user_text)
    buyer_signal = detect_buyer_signal(user_text)

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

    if action == "A_COOLDOWN":
        upsert_state(
            user_id,
            {
                "Profile JSON": json.dumps(profile, ensure_ascii=False),
                "Cooldown Until": (now + datetime.timedelta(minutes=COOLDOWN_MINUTES_ON_SAFE_LIMIT)).isoformat(),
            },
        )
        return

    # --- OFFER hook (still placeholder) ---
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

    # --- SHIFT (kept, but now language is mostly LLM) ---
    if action == "A_SHIFT" and not waiting_slot:
        last_shift_ts_str = profile.get("__last_shift_ts")
        last_shift_ts = _parse_airtable_dt(last_shift_ts_str) if last_shift_ts_str else None

        if last_shift_ts and (now - last_shift_ts).total_seconds() < SHIFT_MIN_SECONDS_BETWEEN:
            action = "A_CONVERSE"
        else:
            palier = int(profile.get("palier") or 1)
            palier = max(1, min(palier, 4))

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
                profile["palier"] = min(4, palier + 1)

            profile["__last_shift_ts"] = now.isoformat()
            profile["safe_turns"] = 0

            await human_delay()
            await bot.send_message(user_id, shift_msg)
            await _log_staff(bot, topic_id, f"[AUTO][SHIFT][{variant}] → {shift_msg}")

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

        # If user says "et toi ..." while we're waiting, answer Jessie + reask waiting slot
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

                # natural reask via LLM
                llm_msg = await llm_generate("reask_slot", waiting_slot, profile, user_text)
                msg_out = llm_msg or fallback_slot_question(waiting_slot, profile, mode="reask")

                final_out = f"{et_toi_reply} {msg_out}".strip()

                await human_delay()
                await bot.send_message(user_id, final_out)
                await _log_staff(bot, topic_id, f"[AUTO][ET_TOI+REASK][{waiting_slot}] → {final_out}")

                profile.pop("__pending_et_toi_slot", None)
                upsert_state(
                    user_id,
                    {
                        "Profile JSON": json.dumps(profile, ensure_ascii=False),
                        "Cooldown Until": (now + datetime.timedelta(seconds=COOLDOWN_SECONDS)).isoformat(),
                    },
                )
                return

        # "et toi ?" only
        if asked and pure_et_toi:
            et_toi_slot = pending or last_question_slot
            et_toi_reply = answer_et_toi(et_toi_slot)

            if pending:
                profile.pop("__pending_et_toi_slot", None)

            llm_msg = await llm_generate("reask_slot", waiting_slot, profile, user_text)
            msg_out = llm_msg or fallback_slot_question(waiting_slot, profile, mode="reask")

            final_out = f"{et_toi_reply} {msg_out}".strip()
            await human_delay()
            await bot.send_message(user_id, final_out)
            await _log_staff(bot, topic_id, f"[AUTO][ET_TOI][REASK][{waiting_slot}] → {final_out}")

            upsert_state(
                user_id,
                {
                    "Profile JSON": json.dumps(profile, ensure_ascii=False),
                    "Cooldown Until": (now + datetime.timedelta(seconds=COOLDOWN_SECONDS)).isoformat(),
                },
            )
            return

        # Try to fill slot
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

        # Not filled -> LLM reask
        if not filled:
            llm_msg = await llm_generate("reask_slot", waiting_slot, profile, user_text)
            msg_out = llm_msg or fallback_slot_question(waiting_slot, profile, mode="reask")

            await human_delay()
            await bot.send_message(user_id, msg_out)
            await _log_staff(bot, topic_id, f"[AUTO][REASK][{waiting_slot}] → {msg_out}")

            upsert_state(
                user_id,
                {
                    "Profile JSON": json.dumps(profile, ensure_ascii=False),
                    "Cooldown Until": (now + datetime.timedelta(seconds=COOLDOWN_SECONDS)).isoformat(),
                },
            )
            return

        # Slot filled -> soft ack + next ask_slot (LLM)
        ack = pick_soft_ack(profile)

        prefix_parts = []
        if asked:
            prefix_parts.append(answer_et_toi(waiting_slot))
        prefix_parts.append(ack)

        profile["__prefix_next"] = " ".join(prefix_parts).strip()

        # decide next slot to ask (simple deterministic order)
        # you can tweak priority here
        order = ["prenom", "ville", "age", "metier", "celibataire"]
        for s in order:
            if s not in profile:
                profile["__waiting_slot"] = s
                profile["__last_question_slot"] = s
                break
        else:
            profile["__waiting_slot"] = None

        upsert_state(
            user_id,
            {
                "Profile JSON": json.dumps(profile, ensure_ascii=False),
            },
        )

    # ---------------- B) Ask next slot or smalltalk ----------------
    prefix = profile.pop("__prefix_next", None)
    waiting_slot = profile.get("__waiting_slot")

    if waiting_slot:
        llm_msg = await llm_generate("ask_slot", waiting_slot, profile, user_text)
        msg_out = llm_msg or fallback_slot_question(waiting_slot, profile, mode="ask")
        if prefix:
            msg_out = f"{prefix} {msg_out}".strip()

        await human_delay()
        await bot.send_message(user_id, msg_out)
        await _log_staff(bot, topic_id, f"[AUTO][ASK_SLOT][{waiting_slot}] → {msg_out}")

        upsert_state(
            user_id,
            {
                "Profile JSON": json.dumps(profile, ensure_ascii=False),
                "Cooldown Until": (now + datetime.timedelta(seconds=COOLDOWN_SECONDS)).isoformat(),
            },
        )
        return

    # No waiting slot: smalltalk natural
    llm_msg = await llm_generate("smalltalk", None, profile, user_text)
    msg_out = llm_msg or "Haha ok 😌"

    # handle "et toi ?" outside slot flow
    if asked:
        et_toi_slot = profile.get("__last_filled_slot") or profile.get("__last_question_slot")
        msg_out = f"{answer_et_toi(et_toi_slot)} {msg_out}".strip()

    await human_delay()
    await bot.send_message(user_id, msg_out)
    await _log_staff(bot, topic_id, f"[AUTO][SMALLTALK] → {msg_out}")

    upsert_state(
        user_id,
        {
            "Profile JSON": json.dumps(profile, ensure_ascii=False),
            "Cooldown Until": (now + datetime.timedelta(seconds=COOLDOWN_SECONDS)).isoformat(),
        },
    )
