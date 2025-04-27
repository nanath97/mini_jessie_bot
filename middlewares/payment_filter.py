from aiogram import types
from aiogram.dispatcher.middlewares import BaseMiddleware
from aiogram.dispatcher.handler import CancelHandler

class PaymentFilterMiddleware(BaseMiddleware):
    def __init__(self, authorized_users):
        super(PaymentFilterMiddleware, self).__init__()
        self.authorized_users = authorized_users

    async def on_pre_process_message(self, message: types.Message, data: dict):
        if message.text and message.text.startswith("/start"):
            return  # Laisser passer /start normal
        
        if message.from_user.id not in self.authorized_users:
            try:
                await message.bot.delete_message(chat_id=message.chat.id, message_id=message.message_id)
            except Exception as e:
                print(f"Erreur suppression message non autorisé : {e}")
            await message.bot.send_message(
                message.chat.id,
                "🚫 Merci de souscrire à un accès VIP ou d’acheter un contenu pour pouvoir discuter."
            )
            raise CancelHandler()
