from aiogram import Bot, Dispatcher
from aiogram.contrib.fsm_storage.memory import MemoryStorage
import os
from dotenv import load_dotenv
from middlewares.payment_filter import PaymentFilterMiddleware

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")

bot = Bot(token=BOT_TOKEN)
bot.set_current(bot)

storage = MemoryStorage()
dp = Dispatcher(bot, storage=storage)

# Middleware
authorized_users = set()
dp.middleware.setup(PaymentFilterMiddleware(authorized_users))
