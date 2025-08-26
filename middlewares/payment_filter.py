# middlewares/payment_filter.py
from aiogram import types
from aiogram.dispatcher.middlewares import BaseMiddleware
from aiogram.dispatcher.handler import CancelHandler
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from detect_links_whitelist import lien_non_autorise
from ban_storage import ban_list

import asyncio
import time

ADMIN_ID = 7334072965

BOUTONS_AUTORISES = [
    "🔞 Voir le contenu du jour...en jouant 🎰",
    "✨Discuter en tant que VIP",
]

# ----- Quota messages gratuits (non-VIP) -----
FREE_MSGS_LIMIT = 5
FREE_MSGS_WINDOW_SECONDS = 24 * 3600
SHOW_REMAINING_HINT = True

VIP_URL = "https://buy.stripe.com/dRm28q3SB7Zd9wx9XL7AI0m"

# État quota par utilisateur : user_id -> {"count": int, "window_start": float, "last": float}
free_msgs_state = {}

# ----- Anti-doublon par message -----
RECENT_CACHE_TTL = 90  # secondes
_recent_decisions = {}  # (chat_id, message_id) -> (cancel: bool, ts: float)

def _remember_decision(key, cancel, now):
    _recent_decisions[key] = (cancel, now)
    # petit nettoyage
    if len(_recent_decisions) > 5000:
        cutoff = now - RECENT_CACHE_TTL
        for k, (_, ts) in list(_recent_decisions.items()):
            if ts < cutoff:
                del _recent_decisions[k]

def reset_free_quota(user_id: int):
    """Appelée quand l'utilisateur devient VIP (/start=cdanXX ou /start=vipcdan)."""
    free_msgs_state.pop(user_id, None)


class PaymentFilterMiddleware(BaseMiddleware):
    def __init__(self, authorized_users):
        super().__init__()
        self.authorized_users = authorized_users

    async def on_pre_process_message(self, message: types.Message, data: dict):
        user_id = message.from_user.id
        now = time.time()

        # ---------- Anti-doublon ----------
        key = (message.chat.id, message.message_id)
        memo = _recent_decisions.get(key)
        if memo is not None:
            cancel, _ = memo
            if cancel:
                raise CancelHandler()
            return

        # ---------- Ban ----------
        for admin_id, clients_bannis in ban_list.items():
            if user_id in clients_bannis:
                try:
                    await message.delete()
                except Exception as e:
                    print(f"Erreur suppression message banni : {e}")
                try:
                    await message.answer("🚫 Tu as été banni. Tu ne peux plus envoyer de message.")
                except Exception as e:
                    print(f"Erreur envoi message banni : {e}")
                _remember_decision(key, True, now)
                raise CancelHandler()

        # On ne filtre que le TEXT ici
        if message.content_type != types.ContentType.TEXT:
            _remember_decision(key, False, now)
            return

        # ---------- Admin : vérifier les liens uniquement ----------
        if user_id == ADMIN_ID:
            if lien_non_autorise(message.text):
                try:
                    await message.delete()
                    await message.answer("🚫 Seuls les liens autorisés sont acceptés.")
                except Exception as e:
                    print(f"Erreur suppression lien admin : {e}")
                _remember_decision(key, True, now)
                raise CancelHandler()
            _remember_decision(key, False, now)
            return

        # ---------- Laisser passer /start ----------
        if message.text and message.text.startswith("/start"):
            _remember_decision(key, False, now)
            return

        # ---------- Laisser passer les boutons prédéfinis ----------
        if message.text.strip() in BOUTONS_AUTORISES:
            _remember_decision(key, False, now)
            return

        # =========================
        # 🚫 NON-VIP : 5 messages gratuits / 24h, puis paywall
        # =========================
        if user_id not in self.authorized_users:
            state = free_msgs_state.get(user_id)

            # Reset si fenêtre expirée ou première fois
            if (not state) or (now - state.get("window_start", 0) > FREE_MSGS_WINDOW_SECONDS):
                state = {"count": 0, "window_start": now}

            # Incrémenter pour CE message (protégé par anti-doublon)
            state["count"] += 1
            state["last"] = now
            free_msgs_state[user_id] = state

            if state["count"] <= FREE_MSGS_LIMIT:
                # Petit rappel "X/5"
                if SHOW_REMAINING_HINT:
                    remaining = FREE_MSGS_LIMIT - state["count"]
                    hint = (
                        f"💬 Message gratuit utilisé ({state['count']}/{FREE_MSGS_LIMIT})."
                        f"{' Il t’en reste ' + str(remaining) + '.' if remaining > 0 else ' C’était le dernier gratuit 😉'}"
                    )
                    asyncio.create_task(
                        message.bot.send_message(chat_id=message.chat.id, text=hint)
                    )
                _remember_decision(key, False, now)  # laisser passer vers tes handlers
                return

            # Quota dépassé → push VIP + bloquer
            pay_kb = InlineKeyboardMarkup().add(
                InlineKeyboardButton("💎 Devenir VIP maintenant", url=VIP_URL)
            )
            await message.bot.send_message(
                chat_id=message.chat.id,
                text=(
                    "🚪 Tu as utilisé tes 5 messages gratuits.\n"
                    "Pour continuer à discuter librement et avoir mes réponses prioritaires, "
                    "rejoins mon espace VIP 💕."
                ),
                reply_markup=pay_kb
            )
            _remember_decision(key, True, now)
            raise CancelHandler()

        # ---------- VIP : on laisse passer ----------
        _remember_decision(key, False, now)
        return
    


# après création de dp
if not getattr(dp, "_pfm_installed", False):
    dp.middleware.setup(PaymentFilterMiddleware(authorized_users))
    dp._pfm_installed = True
