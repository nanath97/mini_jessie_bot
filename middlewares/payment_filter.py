from detect_links_whitelist import lien_non_autorise  # Pour filtrer les liens
from aiogram import types
from aiogram.dispatcher.middlewares import BaseMiddleware
from aiogram.dispatcher.handler import CancelHandler
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from ban_storage import ban_list  # Import de la ban_list

import asyncio
import time  # pour la fenêtre glissante

ADMIN_ID = 7334072965  # Ton ID Telegram admin

BOUTONS_AUTORISES = [
    "🔞 See today's content...while playing 🎰",
    "✨Chat as a VIP",
]

# ===== Paramètres "messages gratuits" =====
FREE_MSGS_LIMIT = 5                          # nombre de messages gratuits
FREE_MSGS_WINDOW_SECONDS = 24 * 3600         # fenêtre glissante de 24h
SHOW_REMAINING_HINT = True                   # afficher "X/5 utilisés" au fil de l'eau
free_msgs_state = {}                         # user_id -> {"count": int, "window_start": float, "last": float}

# Lien VIP (existant)
VIP_URL = "https://buy.stripe.com/dRm28q3SB7Zd9wx9XL7AI0m"

# ===== Anti-doublon par message =====
# clé = (chat_id, message_id) → timestamp
_processed_keys = {}
_PROCESSED_TTL = 60  # secondes

def _prune_processed(now: float):
    # Nettoyage simple pour éviter l'accumulation en mémoire
    for k, ts in list(_processed_keys.items()):
        if now - ts > _PROCESSED_TTL:
            del _processed_keys[k]

# (Anciennes fonctions de nudge conservées mais non utilisées ; tu peux les supprimer si tu veux)
async def send_nonvip_reply_after_delay(bot, chat_id: int, user_id: int, authorized_users, delay_seconds: int = 13):
    await asyncio.sleep(delay_seconds)
    if user_id in authorized_users:
        return
    await bot.send_message(
        chat_id=chat_id,
        text=(
            "Nice to meet you, my dear,\n\nActually, I would love to get to know you and show you more 🔞 but you have to be a VIP !\n\n"
            "Plus, instead of €9, it's only €1 today! I'll be waiting for you on the other side....🤭\n\n"
            "<i>🔐 Secure payment via Stripe</i>\n\n"
            f"{VIP_URL} \n\n"
        ),
        reply_markup=InlineKeyboardMarkup().add(
            InlineKeyboardButton(text="💎 Become a VIP now", url=VIP_URL)
        ),
        parse_mode="HTML"
    )

async def send_nonvip_second_reply_after_delay(bot, chat_id: int, user_id: int, authorized_users, delay_seconds: int = 13):
    await asyncio.sleep(delay_seconds)
    if user_id in authorized_users:
        return
    await bot.send_message(
        chat_id=chat_id,
        text=(
            "My heart 💕, Actually, what I want is not to reveal myself for nothing! I really want to be myself so that I can answer you, "
            "you have to be in my VIP area 💎. I'll be waiting for you there… 🤭\n\n"
            "<i>🔐 Secure payment via Stripe</i>\n\n"
            f"{VIP_URL} \n\n"
        ),
        reply_markup=InlineKeyboardMarkup().add(
            InlineKeyboardButton(text="💎 Become a VIP now", url=VIP_URL)
        ),
        parse_mode="HTML"
    )

# Helper facultatif : à appeler quand un user devient VIP pour nettoyer son compteur
def reset_free_quota(user_id: int):
    free_msgs_state.pop(user_id, None)


class PaymentFilterMiddleware(BaseMiddleware):
    def __init__(self, authorized_users):
        super(PaymentFilterMiddleware, self).__init__()
        self.authorized_users = authorized_users

    async def on_pre_process_message(self, message: types.Message, data: dict):
        user_id = message.from_user.id

        # 🔒 Anti-doublon: s'assurer qu'on ne compte/envoie qu'une fois par message
        now = time.time()
        _prune_processed(now)
        key = (message.chat.id, message.message_id)
        if key in _processed_keys:
            # ce même message a déjà été traité par le middleware → ne pas re-compter ni re-notifier
            return
        _processed_keys[key] = now

        # 🔒 Banni → supprimer + notifier
        for admin_id, clients_bannis in ban_list.items():
            if user_id in clients_bannis:
                try:
                    await message.delete()
                except Exception as e:
                    print(f"Erreur suppression message banni : {e}")
                try:
                    await message.answer("🚫 You have been banned. You can no longer send messages.")
                except Exception as e:
                    print(f"Erreur envoi message banni : {e}")
                raise CancelHandler()

        # Ne gérer que du texte
        if message.content_type != types.ContentType.TEXT:
            return

        # ✅ Admin : juste filtrage des liens
        if user_id == ADMIN_ID:
            if lien_non_autorise(message.text):
                try:
                    await message.delete()
                    await message.answer("🚫 Seuls les liens autorisés sont acceptés.")
                except Exception as e:
                    print(f"Erreur suppression lien admin : {e}")
                raise CancelHandler()
            return

        # ✅ Autoriser /start
        if message.text and message.text.startswith("/start"):
            return

        # ✅ Autoriser les boutons prédéfinis
        if message.text.strip() in BOUTONS_AUTORISES:
            return

        # =========================
        # 🚫 NON-VIP : 5 messages gratuits / 24h, puis paywall VIP
        # =========================
        if user_id not in self.authorized_users:
            state = free_msgs_state.get(user_id)

            # Reset si première fois OU fenêtre expirée
            if (not state) or (now - state.get("window_start", 0) > FREE_MSGS_WINDOW_SECONDS):
                state = {"count": 0, "window_start": now}

            # Incrémenter pour CE message (une seule fois grâce à l'anti-doublon)
            state["count"] += 1
            state["last"] = now
            free_msgs_state[user_id] = state

            if state["count"] <= FREE_MSGS_LIMIT:
                # Option : petit rappel "X/5"
                if SHOW_REMAINING_HINT:
                    remaining = FREE_MSGS_LIMIT - state["count"]
                    hint = (
                        f"💬 Free message used ({state['count']}/{FREE_MSGS_LIMIT})."
                        f"{' You still have some left ' + str(remaining) + '.' if remaining > 0 else ' It was the last free one 😉'}"
                    )
                    # on envoie en tâche pour ne pas bloquer
                    asyncio.create_task(
                        message.bot.send_message(
                            chat_id=message.chat.id,
                            text=hint,
                            reply_to_message_id=message.message_id  # optionnel: rend le rappel plus lisible
                        )
                    )
                # Laisser passer vers tes handlers normaux
                return

            # Quota dépassé → push VIP + bloquer la propagation
            pay_kb = InlineKeyboardMarkup().add(
                InlineKeyboardButton("💎 Become a VIP now", url=VIP_URL)
            )
            await message.bot.send_message(
                chat_id=message.chat.id,
                text=(
                    "🚪 You have used your 5 free messages.\n"
                    "To continue discussing freely and receive priority responses, "
                    "join my VIP area 💕."
                ),
                reply_markup=pay_kb
            )
            raise CancelHandler()

        # ✅ VIP : on laisse passer
        return
