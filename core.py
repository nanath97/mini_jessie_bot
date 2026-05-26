from aiogram import Bot, Dispatcher
import os
from dotenv import load_dotenv





load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
bot = Bot(token=BOT_TOKEN)
bot.set_current(bot)
dp = Dispatcher(bot)
# ===== AJOUT NOVA PROTECTION PAIEMENT (NE PAS TOUCHER) =====
authorized_users = set()