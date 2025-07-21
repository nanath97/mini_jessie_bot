from detect_links_whitelist import lien_non_autorise  # Pour filtrer les liens
from aiogram import types
from aiogram.dispatcher.middlewares import BaseMiddleware
from aiogram.dispatcher.handler import CancelHandler

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

        
        if message.content_type != types.ContentType.TEXT:
            return
        
        # ➡️ SI c'est l'ADMIN, vérifier uniquement les liens
        if message.from_user.id == ADMIN_ID:
            if lien_non_autorise(message.text):
                try:
                    await message.delete()
                    await message.answer("🚫 Seuls les liens autorisés sont acceptés.")
                except Exception as e:
                    print(f"Erreur suppression lien admin : {e}")
                raise CancelHandler()
            return  # Sinon laisser passer normal

        if message.text and message.text.startswith("/start"):
            return  # Laisser passer /start
        
        if message.text.strip() in BOUTONS_AUTORISES:
            return  # Laisser passer les boutons autorisés
        
        if message.from_user.id not in self.authorized_users:
            try:
                await message.delete()
            except Exception as e:
                print(f"Erreur suppression message non autorisé : {e}")
                await message.answer(
    "🚫 Pour discuter librement avec moi, il faudra être un VIP !\n\n"
    "👇 Clique ci-dessous pour débloquer ton accès immédiat :\n\n"
    "Cela coûte 1€ en paiement unique ! 🎁 Je t'attends...🤭",
    reply_markup=InlineKeyboardMarkup().add(
        InlineKeyboardButton(
            text="💎 Devenir VIP pour 1€",
            url="https://buy.stripe.com/4gwg32fhF4K62fCdQR"
        )
    )
)
            raise CancelHandler()


