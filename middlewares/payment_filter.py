from aiogram import types
from aiogram.dispatcher.middlewares import BaseMiddleware
from aiogram.dispatcher.handler import CancelHandler

BOUTONS_AUTORISES = [
    "🔞 Voir la vidéo du jour",
    "✨ Discuter en tant que VIP",
    "👀 Je suis un voyeur",
    "✅ Oui je confirme (bannir)",  # <-- ton premier sous bouton
    "🚀 Non, je veux rejoindre le VIP"  # <-- ton deuxième sous bouton
]

class PaymentFilterMiddleware(BaseMiddleware):
    def __init__(self, authorized_users):
        super(PaymentFilterMiddleware, self).__init__()
        self.authorized_users = authorized_users

    async def on_pre_process_message(self, message: types.Message, data: dict):
        if message.text and message.text.startswith("/start"):
            return  # Laisser passer /start normal
        
        # >>> NOUVEL AJOUT TRES IMPORTANT
        if message.text in BOUTONS_AUTORISES:
            return  # C'est un bouton connu, on laisse passer
        
        # Si le message vient d'un ReplyKeyboardMarkup (clavier réponse Telegram), laisser passer
        if message.reply_to_message or message.reply_markup:
            return  # Il y a un clavier associé, donc c'est un bouton, on laisse passer
        # <<< FIN AJOUT
        
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
