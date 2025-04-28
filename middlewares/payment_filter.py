from detect_links_whitelist import lien_non_autorise  # Pour filtrer les liens
from aiogram import types
from aiogram.dispatcher.middlewares import BaseMiddleware
from aiogram.dispatcher.handler import CancelHandler


ADMIN_ID = 7334072965  # Remets ici ton vrai ID Telegram admin


BOUTONS_AUTORISES = [
    "🔞Voir la vidéo du jour",
    "✨Discuter en tant que VIP",
    "👀Je suis un voyeur",
    "✅ Oui je confirme (bannir)",  # <-- ton premier sous bouton
    "🚀 Non, je veux rejoindre le VIP"  # <-- ton deuxième sous bouton
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
                    await message.bot.delete_message(chat_id=message.chat.id, message_id=message.message_id)
                    await message.bot.send_message(chat_id=message.chat.id, text="🚫 Seuls les liens autorisés sont acceptés.")
                except Exception as e:
                    print(f"Erreur suppression lien admin : {e}")
                raise CancelHandler()
            return  # Sinon laisser passer normal

        if message.text and message.text.startswith("/start"):
            return  # Laisser passer /start normal
        
        # >>> NOUVEL AJOUT TRES IMPORTANT
        if message.text.strip() in BOUTONS_AUTORISES:
            return
        
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
