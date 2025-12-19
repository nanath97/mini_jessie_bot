# ai_autopilot.py
import os
import json
import random
import datetime
from typing import Dict, Any, Optional, List

from aiogram import types

from ai_state_store import get_state, upsert_state, get_script_json, get_media_candidates
from offer_trigger import trigger_offer
import re
from ai_state_store import get_script_json




def _now_utc():
    return datetime.datetime.utcnow().replace(tzinfo=datetime.timezone.utc)

# --------- CONFIG ----------
COOLDOWN_SECONDS = int(os.getenv("AI_COOLDOWN_SECONDS", "8"))
HEAT_SCRIPT_THRESHOLD = int(os.getenv("AI_HEAT_THRESHOLD", "45"))

# --------- UTIL ----------
def _safe_json_load(s: Optional[str], default):
    try:
        if not s:
            return default
        if isinstance(s, dict):
            return s
        return json.loads(s)
    except Exception:
        return default

def _now_iso():
    return datetime.datetime.utcnow().isoformat()

def _parse_iso(s: Optional[str]) -> Optional[datetime.datetime]:
    if not s:
        return None
    try:
        return datetime.datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception:
        return None

def _clamp(n: int, a: int, b: int) -> int:
    return max(a, min(b, n))

def _inc_heat_from_text(text: str) -> int:
    """
    Heuristique simple (MVP). Tu pourras raffiner plus tard.
    """
    t = (text or "").lower()
    score = 1  # base
    hot = ["sexy", "chaud", "hot", "nue", "photo", "video", "envoye", "montre", "douche", "lingerie", "bb", "bébé", "princesse"]
    money = ["payer", "payé", "stripe", "lien", "acheter", "€", "euros"]
    cold = ["arnaque", "fake", "ia", "robot", "preuve", "gratuit", "free", "snap", "instagram", "numero", "tel"]

    if any(w in t for w in hot):
        score += 3
    if any(w in t for w in money):
        score += 2
    if "?" in t:
        score += 1
    if any(w in t for w in cold):
        score -= 3

    return _clamp(score, -5, 6)

def _pick_stage(heat: int) -> str:
    if heat < 25:
        return "ACQ"
    if heat < 45:
        return "BUILDUP"
    if heat < 70:
        return "SEX"
    return "CLOSE"

def _rand_between(minv: int, maxv: int) -> int:
    return random.randint(minv, maxv)

def _ensure_profile(fields: Dict[str, Any]) -> Dict[str, Any]:
    profile = _safe_json_load(fields.get("Profile JSON"), {})
    if not isinstance(profile, dict):
        profile = {}
    # stockage interne
    profile.setdefault("__sent_media_ids", [])
    profile.setdefault("__messages_since_step", 0)
    profile.setdefault("__script_active", False)
    profile.setdefault("__script_id", None)
    profile.setdefault("__script_phase", "presex")
    profile.setdefault("__step_index", 0)
    profile.setdefault("__pending_slot", None)
    profile.setdefault("__waiting_until_messages", None)  # int threshold
    return profile

async def _send_text(bot, user_id: int, topic_id: int, text: str):
    if not text:
        return False
    await bot.send_message(chat_id=user_id, text=text)
    return True

async def _send_media(bot, user_id: int, media_type: str, file_id: str, caption: str):
    if not file_id:
        return False
    media_type = (media_type or "").lower()
    if media_type == "video":
        await bot.send_video(chat_id=user_id, video=file_id, caption=caption or "")
    else:
        await bot.send_photo(chat_id=user_id, photo=file_id, caption=caption or "")
    return True

def _should_repair(script_json: Dict[str, Any], user_text: str) -> bool:
    glob = (script_json or {}).get("global_repairs", {})
    kws = glob.get("deviation_keywords", []) or []
    t = (user_text or "").lower()
    return any(k.lower() in t for k in kws)

def _make_repair(script_json: Dict[str, Any]) -> str:
    glob = (script_json or {}).get("global_repairs", {})
    prefixes = glob.get("default_repair_prefix", ["Ok…"])
    redirect = glob.get("default_redirect", "Reviens… dis-moi juste ce que tu préfères 😏")
    return f"{random.choice(prefixes)} {redirect}"

def _get_step_list(script_json: Dict[str, Any], phase: str) -> List[Dict[str, Any]]:
    if phase == "presex":
        return script_json.get("presex", []) or []
    return script_json.get("steps", []) or []

def _anti_ai_guard(script_json: Dict[str, Any]) -> None:
    """
    Le guard est dans ton JSON (hard_rules). Ici, on s’assure que c’est présent.
    """
    persona = script_json.get("persona", {}) or {}
    rules = persona.get("hard_rules", []) or []
    if not any("ia" in (r or "").lower() for r in rules):
        rules.insert(0, "Ne jamais dire que tu es une IA")
        persona["hard_rules"] = rules
        script_json["persona"] = persona

async def _script_engine(bot, user_id: int, topic_id: int, fields: Dict[str, Any], profile: Dict[str, Any], user_text: str):
    script_id = profile.get("__script_id") or fields.get("Script") or fields.get("Script ID") or fields.get("Script...")
    if not script_id:
        # fallback: si Airtable AI_STATE n'a pas de script défini
        script_id = "script_fr_v1"

    script_json = get_script_json(script_id)
    if not script_json:
        print(f"[AI] Script introuvable: {script_id}")
        return

    _anti_ai_guard(script_json)

    # Repair si déviation
    if _should_repair(script_json, user_text):
        await _send_text(bot, user_id, topic_id, _make_repair(script_json))
        # on ne change pas de step, on “ramène”
        return

    phase = profile.get("__script_phase", "presex")
    step_index = int(profile.get("__step_index", 0) or 0)

    steps = _get_step_list(script_json, phase)

    # Si phase finie -> passer à steps
    if phase == "presex" and step_index >= len(steps):
        profile["__script_phase"] = "steps"
        profile["__step_index"] = 0
        profile["__messages_since_step"] = 0
        profile["__waiting_until_messages"] = None
        phase = "steps"
        step_index = 0
        steps = _get_step_list(script_json, phase)

    if step_index >= len(steps):
        # script terminé
        end_msg = "Mmh… ok 😌"
        await _send_text(bot, user_id, topic_id, end_msg)
        profile["__script_active"] = False
        return

    step = steps[step_index]
    stype = step.get("type", "text")

    # Gestion "between_messages"
    between = step.get("between_messages")
    if between and isinstance(between, dict):
        # Si pas encore de seuil, on le fixe une fois
        if profile.get("__waiting_until_messages") is None:
            profile["__waiting_until_messages"] = _rand_between(int(between.get("min", 1)), int(between.get("max", 2)))
            profile["__messages_since_step"] = 0

        # On attend d’avoir assez de messages client
        if int(profile.get("__messages_since_step", 0)) < int(profile["__waiting_until_messages"]):
            return

    # Step "ask" = pose question + attend réponse (slot)
    if stype == "ask":
        slot = step.get("slot") or "slot"
        # Si on n’attend pas encore ce slot, on pose la question
        if profile.get("__pending_slot") != slot:
            msg = step.get("message", "")
            await _send_text(bot, user_id, topic_id, msg)
            profile["__pending_slot"] = slot
            # on ne passe pas au step suivant tant qu’on n’a pas une réponse
            return
        else:
            # on a reçu une réponse utilisateur → on enregistre et on avance
            profile[slot] = user_text
            profile["__pending_slot"] = None
            profile["__step_index"] = step_index + 1
            profile["__messages_since_step"] = 0
            profile["__waiting_until_messages"] = None
            return

    # Step "text"
    if stype == "text":
        msg = step.get("message", "")
        await _send_text(bot, user_id, topic_id, msg)
        profile["__step_index"] = step_index + 1
        profile["__messages_since_step"] = 0
        profile["__waiting_until_messages"] = None
        return

    # Step "media_push"
    if stype == "media_push":
        list_id = step.get("media_list_id")
        caption = step.get("caption", "") or ""

        # stage -> on peut filtrer, sinon on prend tout
        stage = step.get("stage")  # optionnel
        candidates = get_media_candidates(list_id=list_id, stage=stage, limit=30)

        sent_ids = set(profile.get("__sent_media_ids", []) or [])

        # filtrer file_id vide + déjà envoyés
        candidates = [c for c in candidates if c.get("file_id") and c.get("media_id") and c.get("media_id") not in sent_ids]
        if not candidates:
            # fallback: sans filtre "déjà envoyés"
            candidates = get_media_candidates(list_id=list_id, stage=stage, limit=10)
            candidates = [c for c in candidates if c.get("file_id")]

        if not candidates:
            await _send_text(bot, user_id, topic_id, "Oups… attends 2 sec 😅")
            profile["__step_index"] = step_index + 1
            return

        chosen = random.choice(candidates)
        desc_short = chosen.get("desc_short") or ""
        final_caption = caption
        if desc_short:
            final_caption = (caption + "\n\n" + desc_short).strip()

        await _send_media(bot, user_id, chosen.get("media_type") or "photo", chosen["file_id"], final_caption)

        # log
        mid = chosen.get("media_id")
        if mid:
            profile["__sent_media_ids"] = (profile.get("__sent_media_ids", []) or []) + [mid]

        profile["__step_index"] = step_index + 1
        profile["__messages_since_step"] = 0
        profile["__waiting_until_messages"] = None
        return

    # Step "offer"
    if stype == "offer":
        pre = step.get("pre_teaser", "")
        if pre:
            await _send_text(bot, user_id, topic_id, pre)

        offer_code = str(step.get("offer_code") or "").strip()
        if offer_code:
            await trigger_offer(bot, user_id, offer_code, origin="AI")

        after = step.get("message_after", "")
        if after:
            await _send_text(bot, user_id, topic_id, after)

        profile["__step_index"] = step_index + 1
        profile["__messages_since_step"] = 0
        profile["__waiting_until_messages"] = None
        return

    # Step "end"
    if stype == "end":
        msg = step.get("message", "Ok 😌")
        await _send_text(bot, user_id, topic_id, msg)
        profile["__script_active"] = False
        return








async def _core_reply(bot, user_id: int, fields: dict, profile: dict, user_text: str):
    """
    Réponse simple tant que le script n'est pas actif.
    1-2 phrases, naturel, 1 question max.
    """
    # Mini fallback si tu veux ultra simple (sans OpenAI) :
    # await bot.send_message(user_id, "Hey 😇 oui je suis là... tu fais quoi là ?")

    # Version OpenAI (recommandée)
    script_id = fields.get("Script") or fields.get("Script ID") or "script_fr_v1"
    script_json = get_script_json(script_id) or {}
    persona = (script_json.get("persona") or {})
    name = persona.get("name", "Jessie")
    tone = persona.get("tone", "naturel, teasing, réponses courtes")

    bundle = (profile.get("__bundle_text") or "").strip()
    bundle_tail = "\n".join(bundle.splitlines()[-8:]).strip()

    system = (
        f"Tu es {name}, une créatrice de contenu sur Telegram.\n"
        f"Style: {tone}.\n"
        f"Règles: jamais dire que tu es une IA. 1 question max. Réponse courte (1-2 phrases).\n"
        f"Si l'utilisateur pose une question, réponds d'abord, puis enchaîne.\n"
    )

    user_prompt = (
        f"Contexte (derniers messages):\n{bundle_tail}\n\n"
        f"Message utilisateur: {user_text}\n\n"
        f"Réponds maintenant."
    )

    try:
        resp = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.9,
            max_tokens=120,
        )
        reply = (resp.choices[0].message.content or "").strip()
        if reply:
            await bot.send_message(user_id, reply)
            profile["__last_ai_text"] = reply
    except Exception as e:
        print(f"[CORE_REPLY] error: {e}")






















async def maybe_run_autopilot(user_id: int, topic_id: int, bot):
    """
    Appelé depuis bott_webhook.run_autopilot_safe()
    """
    st = get_state(user_id)
    if not st:
        return

    fields = st.get("fields", {})

    # ✅ DEBUG (OK ici: user_id + fields existent)
    print("[DBG] maybe_run_autopilot: user_id=", user_id)
    print("[DBG] Autopilot=", repr(fields.get("Autopilot")),
          "Heat=", repr(fields.get("Heat")),
          "Script=", repr(fields.get("Script")))

    # 1) Autopilot switch
    if (fields.get("Autopilot") or "").strip().upper() != "ON":
        return

    # 2) Cooldown global
    cd = _parse_iso(fields.get("Cooldown Until"))
    if cd and _now_utc() < cd:
        return

    profile = _ensure_profile(fields)
    user_text = (profile.get("__last_user_text") or "").strip()

    # ✅ DEBUG (OK ici: user_text existe)
    print("[DBG] user_text=", repr(user_text))

    # 3) Update heat
    current_heat = int(fields.get("Heat") or 0)
    delta = _inc_heat_from_text(user_text)
    new_heat = _clamp(current_heat + delta, 0, 100)

    # 4) Update stage
    stage = _pick_stage(new_heat)

    # 5) Count messages since step (pour between_messages)
    profile["__messages_since_step"] = int(profile.get("__messages_since_step", 0)) + 1

    # 6) Trigger script
    if (not profile.get("__script_active")) and new_heat >= HEAT_SCRIPT_THRESHOLD:
        profile["__script_active"] = True
        profile["__script_id"] = fields.get("Script") or fields.get("Script ID") or fields.get("Script...") or "script_fr_v1"
        profile["__script_phase"] = "presex"
        profile["__step_index"] = 0
        profile["__pending_slot"] = None
        profile["__messages_since_step"] = 0
        profile["__waiting_until_messages"] = None

    print("[DBG] new_heat=", new_heat,
          "script_active=", profile.get("__script_active"),
          "script_id=", profile.get("__script_id"),
          "step=", profile.get("__step_index"))


    # 7) Si script actif -> ScriptEngine
    if profile.get("__script_active"):
        await _script_engine(bot, user_id, topic_id, fields, profile, user_text)
    else:
        await _core_reply(bot, user_id, fields, profile, user_text)


    # 8) Persist state
    upsert_state(user_id, {
        "Heat": new_heat,
        "Profile JSON": json.dumps(profile, ensure_ascii=False),
        "Cooldown Until": (_now_utc() + datetime.timedelta(seconds=COOLDOWN_SECONDS)).isoformat()

    })
