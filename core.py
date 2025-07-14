from aiogram import Bot, Dispatcher
from aiogram.contrib.fsm_storage.memory import MemoryStorage
import os
from dotenv import load_dotenv
from middlewares.payment_filter import PaymentFilterMiddleware

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")

bot = Bot(token=BOT_TOKEN)
bot.set_current(bot)

# ✅ Ajout du MemoryStorage pour le FSM
storage = MemoryStorage()

# ✅ Dispatcher avec storage utilisé dans tout le projet
dp = Dispatcher(bot, storage=storage)

# ===== AJOUT NOVA PROTECTION PAIEMENT (NE PAS TOUCHER) =====
authorized_users = set()

# ===== Activation du middleware =====
dp.middleware.setup(PaymentFilterMiddleware(authorized_users))
