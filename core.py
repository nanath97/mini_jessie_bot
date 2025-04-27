from aiogram import Bot, Dispatcher
import os
from dotenv import load_dotenv
from middlewares.payment_filter import PaymentFilterMiddleware
from bott_webhook import authorized_users


load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(bot)
dp.middleware.setup(PaymentFilterMiddleware(authorized_users))
