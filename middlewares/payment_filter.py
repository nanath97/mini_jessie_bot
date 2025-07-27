from detect_links_whitelist import lien_non_autorise  # Pour filtrer les liens
from aiogram import types
from aiogram.dispatcher.middlewares import BaseMiddleware
from aiogram.dispatcher.handler import CancelHandler
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from bott_webhook import ban_list  # Import de la ban_list


ADMIN_ID = 7334072965  # Ton ID Telegram admin

BOUTONS_AUTORISES = [
    "🔞 Voir le contenu du jour",
    "✨Discuter en tant que VIP",
    "👀Je suis un voyeur",
    "❌ Oui je confirme (bannir)",
    "✅ Non, je veux rejoindre le VIP"
]

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

        # ❌ Si utilisateur non VIP → suppression + message + bouton Stripe
        if user_id not in self.authorized_users:
            try:
                await message.delete()
            except Exception as e:
                print(f"Erreur suppression message non autorisé : {e}")

            await message.answer(
                "🚫 Pour discuter librement avec moi, il faudra être un VIP !\n\n"
                "👇 Clique ci-dessous pour débloquer ton accès immédiat :\n\n"
                "Cela coûte 1€ en paiement unique ! 🎁 Je t'attends...🤭\n\n"
                "<i>🔐 Paiement sécurisé par Stripe</i>",
                reply_markup=InlineKeyboardMarkup().add(
                    InlineKeyboardButton(
                        text="💎 Devenir VIP pour 1€",
                        url="https://buy.stripe.com/4gwg32fhF4K62fCdQR"
                    )
                ),
                parse_mode="HTML"
            )
            raise CancelHandler()
