from aiogram import types
from bott_webhook import dp,bot
import re
import os

# Lire les domaines autorisés depuis .env
allowed_domains = os.getenv("ALLOWED_DOMAINS", "")
DOMAINS_AUTORISES = [d.strip() for d in allowed_domains.split(",") if d]

ADMIN_ID = int(os.getenv("ADMIN_TELEGRAM_ID"))

@dp.message_handler(lambda message: "http" in message.text or "https://" in message.text)
async def detect_external_links(message: types.Message):
    liens = re.findall(r"https?://[^\s]+", message.text)
    for lien in liens:
        if not any(domain in lien for domain in DOMAINS_AUTORISES):
            alert_text = (
                f"⚠️ *Lien NON autorisé détecté !*\n\n"
                f"Utilisateur : @{message.from_user.username} (ID: {message.from_user.id})\n"
                f"Message : {message.text}"
            )
            await bot.send_message(chat_id=ADMIN_ID, text=alert_text, parse_mode="Markdown")
            break