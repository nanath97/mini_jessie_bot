# staff_system.py — aiogram 2.22.x
import os, json, asyncio
from typing import Dict, Any, Optional
from aiogram import types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.exceptions import RetryAfter, ChatNotFound

STAFF_FEATURE_ENABLED = os.getenv("STAFF_FEATURE_ENABLED", "false").lower() == "true"
STAFF_GROUP_ID = int(os.getenv("STAFF_GROUP_ID", "0"))
MAP_PATH = os.getenv("STAFF_MAP_PATH", "vip_threads.json")  # persistance légère

# { str(user_id): {"topic_id": int, "owner_id": Optional[int], "username": str, "email": str, "total": float} }
_map: Dict[str, Dict[str, Any]] = {}

# ---------- persistance ----------
def _load_map():
    global _map
    try:
        with open(MAP_PATH, "r", encoding="utf-8") as f:
            _map = json.load(f)
    except FileNotFoundError:
        _map = {}
    except Exception as e:
        print(f"[staff] load map error: {e}")
        _map = {}

def _save_map():
    try:
        with open(MAP_PATH, "w", encoding="utf-8") as f:
            json.dump(_map, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[staff] save map error: {e}")

def _get(uid: int) -> Optional[Dict[str, Any]]:
    return _map.get(str(uid))

def _set(uid: int, data: Dict[str, Any]):
    _map[str(uid)] = data
    _save_map()

# ---------- UI ----------
def _kb(claimed: bool) -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup(row_width=2)
    if claimed:
        kb.add(
            InlineKeyboardButton("🔓 Relâcher", callback_data="staff_release"),
            InlineKeyboardButton("📌 Note", callback_data="staff_note"),
        )
    else:
        kb.add(
            InlineKeyboardButton("🖐️ Prendre en charge", callback_data="staff_claim"),
            InlineKeyboardButton("📌 Note", callback_data="staff_note"),
        )
    return kb

def _mask_email(e: str) -> str:
    if not e or "@" not in e: return e or "—"
    name, dom = e.split("@", 1)
    name_mask = name[0] + "*" * max(1, len(name)-2) + (name[-1] if len(name) > 1 else "")
    return f"{name_mask}@{dom}"

# ---------- API publique ----------
async def init(bot):
    if not STAFF_FEATURE_ENABLED or STAFF_GROUP_ID == 0:
        print("[staff] disabled")
        return
    _load_map()
    try:
        await bot.get_chat(STAFF_GROUP_ID)
        print(f"[staff] ready — topics tracked: {len(_map)}")
    except ChatNotFound:
        print("[staff] STAFF_GROUP_ID introuvable")

async def ensure_topic_for(bot, *, user_id: int, username: Optional[str], email: Optional[str] = "", total_spent: float = 0.0):
    """Crée (idempotent) le topic staff pour ce VIP."""
    if not STAFF_FEATURE_ENABLED or STAFF_GROUP_ID == 0:
        return
    entry = _get(user_id)
    if entry and entry.get("topic_id"):
        # mise à jour légère
        entry["username"] = username or entry.get("username") or ""
        if email: entry["email"] = email
        if total_spent: entry["total"] = float(total_spent)
        _set(user_id, entry)
        await _post_update(bot, user_id)
        return

    name = f"VIP: @{username}" if username else f"VIP: {user_id}"
    ft = await bot.create_forum_topic(STAFF_GROUP_ID, name=name)
    topic_id = ft.message_thread_id
    _set(user_id, {"topic_id": topic_id, "owner_id": None, "username": username or "", "email": email or "", "total": float(total_spent or 0.0)})
    await _post_header(bot, user_id)

async def _post_header(bot, user_id: int):
    e = _get(user_id); 
    if not e: return
    text = (
        "📌 *Fiche VIP*\n"
        f"• Nom: {e['username'] or user_id}\n"
        f"• Telegram ID: `{user_id}`\n"
        f"• Email Stripe: {_mask_email(e.get('email',''))}\n"
        f"• Total dépensé: *{float(e.get('total',0.0)):.2f} €*\n\n"
        "➡️ Répondez dans ce topic pour écrire au client."
    )
    await bot.send_message(STAFF_GROUP_ID, text, parse_mode="Markdown", message_thread_id=e["topic_id"], reply_markup=_kb(False))

async def _post_update(bot, user_id: int):
    e = _get(user_id); 
    if not e: return
    await bot.send_message(
        STAFF_GROUP_ID,
        f"🔄 Mise à jour: Email={_mask_email(e.get('email',''))} | Total={float(e.get('total',0.0)):.2f}€",
        message_thread_id=e["topic_id"],
        disable_notification=True
    )

async def mirror_client_to_staff(bot, message: types.Message):
    """Duplique le message privé du VIP vers son topic staff (si mappé)."""
    if not STAFF_FEATURE_ENABLED or STAFF_GROUP_ID == 0:
        return
    e = _get(message.from_user.id)
    if not e: 
        return
    try:
        await bot.copy_message(
            chat_id=STAFF_GROUP_ID,
            from_chat_id=message.chat.id,
            message_id=message.message_id,
            message_thread_id=e["topic_id"]
        )
    except RetryAfter as ra:
        await asyncio.sleep(ra.timeout + 1)
        await bot.copy_message(
            chat_id=STAFF_GROUP_ID,
            from_chat_id=message.chat.id,
            message_id=message.message_id,
            message_thread_id=e["topic_id"]
        )

async def register_staff_handlers(dp, bot):
    """À appeler au startup pour écouter les réponses staff."""
    if not STAFF_FEATURE_ENABLED or STAFF_GROUP_ID == 0:
        return

    @dp.message_handler(lambda m: m.chat.id == STAFF_GROUP_ID and getattr(m, "message_thread_id", None) is not None, content_types=types.ContentTypes.ANY)
    async def _outbound(m: types.Message):
        # retrouve le client par topic_id
        uid = None
        for k, v in _map.items():
            if v.get("topic_id") == m.message_thread_id:
                uid = int(k); break
        if not uid: 
            return

        owner_id = _map[str(uid)].get("owner_id")
        if owner_id and m.from_user and m.from_user.id != owner_id:
            return  # un autre chatter a "pris" ce client

        try:
            if m.text:
                await bot.send_message(uid, m.text)
            elif m.caption and m.photo:
                await bot.send_photo(uid, m.photo[-1].file_id, caption=m.caption)
            elif m.photo:
                await bot.send_photo(uid, m.photo[-1].file_id)
            elif m.document:
                await bot.send_document(uid, m.document.file_id, caption=m.caption or None)
            elif m.video:
                await bot.send_video(uid, m.video.file_id, caption=m.caption or None)
            elif m.voice:
                await bot.send_voice(uid, m.voice.file_id, caption=m.caption or None)
        except Exception as e:
            await bot.send_message(STAFF_GROUP_ID, f"❌ Non délivré: {e}", message_thread_id=m.message_thread_id, disable_notification=True)

    @dp.callback_query_handler(lambda c: c.data in {"staff_claim", "staff_release"})
    async def _claim(c: types.CallbackQuery):
        topic_id = c.message.message_thread_id
        uid = None
        for k, v in _map.items():
            if v.get("topic_id") == topic_id:
                uid = int(k); break
        if not uid:
            return await c.answer("Introuvable", show_alert=True)

        if c.data == "staff_claim":
            _map[str(uid)]["owner_id"] = c.from_user.id
            _save_map()
            await c.message.edit_reply_markup(reply_markup=_kb(True))
            await c.answer("Pris en charge")
        else:
            _map[str(uid)]["owner_id"] = None
            _save_map()
            await c.message.edit_reply_markup(reply_markup=_kb(False))
            await c.answer("Libéré")
