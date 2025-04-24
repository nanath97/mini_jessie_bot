print("Module detect_links_whitelist.py chargé")
from aiogram import types
from bott_webhook import dp, bot
import re
import os

# Lire les domaines autorisés depuis .env
allowed_domains = os.getenv("ALLOWED_DOMAINS", "")
DOMAINS_AUTORISES = [d.strip().lower() for d in allowed_domains.split(",") if d.strip()]

ADMIN_ID = int(os.getenv("ADMIN_TELEGRAM_ID", "0"))

@dp.message_handler(lambda message: message.text and ("http://" in message.text or "https://" in message.text))
async def detect_external_links(message: types.Message):
    liens = re.findall(r"https?://[^\s]+", message.text)
    for lien in liens:
        if not any(domain in lien.lower() for domain in DOMAINS_AUTORISES):
            try:
                await bot.delete_message(chat_id=message.chat.id, message_id=message.message_id)
            except Exception as e:
                await bot.send_message(chat_id=ADMIN_ID, text=f"❌ Erreur suppression du message : {e}")

            alert_text = (
                f"⚠️ *Lien NON autorisé supprimé !*\n\n"
                f"👤 Utilisateur : @{message.from_user.username or 'inconnu'} (ID: {message.from_user.id})\n"
                f"💬 Message : {message.text}"
            )
            await bot.send_message(chat_id=ADMIN_ID, text=alert_text, parse_mode="Markdown")
            break
