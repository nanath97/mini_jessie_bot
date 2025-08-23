from detect_links_whitelist import lien_non_autorise  # Pour filtrer les liens
from aiogram import types
from aiogram.dispatcher.middlewares import BaseMiddleware
from aiogram.dispatcher.handler import CancelHandler
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from ban_storage import ban_list # Import de la ban_list

import asyncio  # ⬅️ déjà là
import time     # NEW: pour fenêtre de 24h

ADMIN_ID = 7334072965  # Ton ID Telegram admin

BOUTONS_AUTORISES = [
    "🔞 Voir le contenu du jour...en jouant 🎰",
    "✨Discuter en tant que VIP",
]

# ---- Nudge non-VIP: 1er message -> auto #1 ; 2e message -> auto #2 ; 3e+ -> silence (reset 24h) ----
NONVIP_NUDGE_RESET_SECONDS = 24 * 3600  # NEW
nonvip_nudge_state = {}  # NEW  # user_id -> {"count": int, "last": timestamp}

# ===== Helper pour l'envoi différé de la réponse non-VIP (1er message) =====
VIP_URL = "https://buy.stripe.com/dRm28q3SB7Zd9wx9XL7AI0m"

async def send_nonvip_reply_after_delay(bot, chat_id: int, user_id: int, authorized_users, delay_seconds: int = 13):
    # Attendre sans bloquer le bot
    await asyncio.sleep(delay_seconds)

    # S’il est devenu VIP entre-temps, on n’envoie plus le message auto
    if user_id in authorized_users:
        return

    await bot.send_message(
        chat_id=chat_id,
        text=(
            "Enchantée mon coeur, en vrai j'adorerais pouvoir faire ta connaissance et que je te montre plus 🔞 mais il faut que tu sois VIP 💎!\n\n"
            "Au lieu de 9€, c'est à 1 € seulement aujourd'hui ! Je t'attends de l'autre côté...🤭\n\n"
            "<i>🔐 Paiement sécurisé par Stripe</i>\n\n"
            f"{VIP_URL} \n\n"
        ),
        reply_markup=InlineKeyboardMarkup().add(
            InlineKeyboardButton(
                text="💎 Devenir VIP maintenant",
                url=VIP_URL
            )
        ),
        parse_mode="HTML"
    )

# ===== Helper pour l'envoi différé de la réponse non-VIP (2e message, TEXTE DIFFÉRENT) =====
async def send_nonvip_second_reply_after_delay(bot, chat_id: int, user_id: int, authorized_users, delay_seconds: int = 13):  # NEW
    await asyncio.sleep(delay_seconds)
    if user_id in authorized_users:
        return

    await bot.send_message(
        chat_id=chat_id,
        text=(
            "Mon cœur 💕, en faite ce que je veux, c'est ne pas me dévoiler pour rien ! Je voudrais vraiment être moi donc pour que je te réponde"
            "il faut être dans mon espace VIP 💎. Je t’y attends… 🤭\n\n"
            "<i>🔐 Paiement sécurisé par Stripe</i>\n\n"
            f"{VIP_URL} \n\n"
        ),
        reply_markup=InlineKeyboardMarkup().add(
            InlineKeyboardButton(
                text="💎 Devenir VIP maintenant",
                url=VIP_URL
            )
        ),
        parse_mode="HTML"
    )


class PaymentFilterMiddleware(BaseMiddleware):
    def __init__(self, authorized_users):
        super(PaymentFilterMiddleware, self).__init__()
        self.authorized_users = authorized_users

    async def on_pre_process_message(self, message: types.Message, data: dict):
        user_id = message.from_user.id

        # 🔒 Vérifier si ce client est banni par un admin
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
                raise CancelHandler()

        if message.content_type != types.ContentType.TEXT:
            return

        # ✅ Autoriser l'admin (vérifie juste les liens)
        if user_id == ADMIN_ID:
            if lien_non_autorise(message.text):
                try:
                    await message.delete()
                    await message.answer("🚫 Seuls les liens autorisés sont acceptés.")
                except Exception as e:
                    print(f"Erreur suppression lien admin : {e}")
                raise CancelHandler()
            return

        # ✅ Autoriser les /start
        if message.text and message.text.startswith("/start"):
            return

        # ✅ Autoriser les boutons prédéfinis
        if message.text.strip() in BOUTONS_AUTORISES:
            return

        # =========================
        # 🚫 CAS NON-VIP (nudge 1 → 2 → silence, reset 24h)
        # - on NE SUPPRIME PAS le message
        # - on NE NOTIFIE PAS l’admin
        # - 1er msg: auto #1 à +13s
        # - 2e msg: auto #2 à +13s
        # - 3e+ msg: silence pendant 24h
        # =========================
        if user_id not in self.authorized_users:
            now = time.time()
            st = nonvip_nudge_state.get(user_id, {"count": 0, "last": 0})

            # Reset si > 24h depuis le dernier message pris en compte
            if st["last"] and (now - st["last"]) > NONVIP_NUDGE_RESET_SECONDS:
                st = {"count": 0, "last": 0}

            st["count"] += 1
            st["last"] = now
            nonvip_nudge_state[user_id] = st

            if st["count"] == 1:
                # 👉 1er message non-VIP: programmer TON message automatique à +13s
                asyncio.create_task(
                    send_nonvip_reply_after_delay(
                        bot=message.bot,
                        chat_id=message.chat.id,
                        user_id=user_id,
                        authorized_users=self.authorized_users,
                        delay_seconds=13
                    )
                )
            elif st["count"] == 2:
                # 👉 2e message non-VIP: programmer un message DIFFÉRENT à +13s
                asyncio.create_task(
                    send_nonvip_second_reply_after_delay(
                        bot=message.bot,
                        chat_id=message.chat.id,
                        user_id=user_id,
                        authorized_users=self.authorized_users,
                        delay_seconds=13
                    )
                )
            # else: 3e+ message dans la fenêtre de 24h → silence (aucune réponse)

            # Stopper le pipeline pour éviter d'autres handlers
            raise CancelHandler()

        # (VIP) -> on laisse passer normalement, rien à changer
