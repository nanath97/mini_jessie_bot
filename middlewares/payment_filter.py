from detect_links_whitelist import lien_non_autorise
from aiogram import types
from aiogram.dispatcher.middlewares import BaseMiddleware
from aiogram.dispatcher.handler import CancelHandler
import os

ADMIN_ID = 7334072965  # ton ID admin (ok ici)

BOUTONS_AUTORISES = [
    "🔞Voir la vidéo du jour",
    "✨Discuter en tant que VIP",
    "👀Je suis un voyeur",
    "❌ Oui je confirme (bannir)",
    "✅ Non, je veux rejoindre le VIP"
]

class PaymentFilterMiddleware(BaseMiddleware):
    def __init__(self, authorized_users):
        super().__init__()
        self.authorized_users = authorized_users
    async def on_pre_process_message(self, message: types.Message, data: dict):

        print(f"[DEBUG MIDDLEWARE] Reçu un message de {message.from_user.id} : {message.content_type}")

    async def on_pre_process_message(self, message: types.Message, data: dict):

        # ✅ Laisse passer tous les messages de l'admin (texte, photo, doc...)
        if message.from_user.id == ADMIN_ID:
            if message.content_type == types.ContentType.TEXT and lien_non_autorise(message.text):
                try:
                    await message.delete()
                    await message.answer("🚫 Seuls les liens autorisés sont acceptés.")
                except Exception as e:
                    print(f"Erreur suppression lien admin : {e}")
                raise CancelHandler()
            return

        # ✅ Autorise /start
        if message.text and message.text.startswith("/start"):
            return

        # ✅ Autorise les boutons classiques
        if message.text and message.text.strip() in BOUTONS_AUTORISES:
            return

        # ✅ Autorise la commande /envgroupe
        if message.text and message.text.startswith("/envgroupe"):
            return

        # ✅ Autorise les photos/vidéos/documents pendant le FSM (pour les VIP seulement ou FSM)
        if message.from_user.id in self.authorized_users:
            return

        # ❌ Sinon, bloque l’accès
        try:
            await message.delete()
        except Exception as e:
            print(f"Erreur suppression message non autorisé : {e}")

        await message.answer("🚫 Pour discuter librement avec moi, il faut être un VIP ! Clique sur le bouton en bas à droite. Cela coûte 1€ en paiement unique. 🎁 Je t’attends...")
        raise CancelHandler()
