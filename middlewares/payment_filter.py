from detect_links_whitelist import lien_non_autorise  # Pour filtrer les liens
from aiogram import types
from aiogram.dispatcher.middlewares import BaseMiddleware
from aiogram.dispatcher.handler import CancelHandler
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from ban_storage import ban_list # Import de la ban_list

import asyncio  # ⬅️ ajouté ici (au lieu de l'avoir au milieu du handler)

ADMIN_ID = 7334072965  # Ton ID Telegram admin

BOUTONS_AUTORISES = [
    "🔞 Voir le contenu du jour...en jouant 🎰",
    "✨Discuter en tant que VIP",
]

# ===== Helper pour l'envoi différé de la réponse non-VIP (phrases inchangées) =====
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
            "🚫 Enchantée mon coeur, j'adorerais pouvoir commenceer à faire ta connaissance et que je te montre plus 🔞 mais il faut que tu sois dans mon espace VIP 💎!\n\n"
            "👇 Clique ci-dessous pour débloquer ton accès immédiat :\n\n"
            "C'est à 1 € seulement aujourd'hui ! 🎁 Je t'attends de l'autre côté...🤭\n\n"
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
        # 🚫 CAS NON-VIP (nouvelle logique)
        # - on NE SUPPRIME PAS le message
        # - on NE NOTIFIE PAS l’admin
        # - on ENVOIE la réponse automatique 13s plus tard
        # - on stoppe le pipeline pour éviter d'autres handlers
        # =========================
        if user_id not in self.authorized_users:
            asyncio.create_task(
                send_nonvip_reply_after_delay(
                    bot=message.bot,
                    chat_id=message.chat.id,
                    user_id=user_id,
                    authorized_users=self.authorized_users,
                    delay_seconds=13
                )
            )
            raise CancelHandler()

        # (VIP) -> on laisse passer normalement, rien à changer
