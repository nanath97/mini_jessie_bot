from aiogram import Bot, Dispatcher
import os
from dotenv import load_dotenv
from middlewares.payment_filter import PaymentFilterMiddleware
from airtable import Airtable
from pyairtable import Table as Airtable



load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
bot = Bot(token=BOT_TOKEN)
bot.set_current(bot)
dp = Dispatcher(bot)
# ===== AJOUT NOVA PROTECTION PAIEMENT (NE PAS TOUCHER) =====
authorized_users = set()
# ===== Activation du middleware =====
dp.middleware.setup(PaymentFilterMiddleware(authorized_users))

def get_all_vip_ids():
    
    from airtable import Airtable

    base_id = os.getenv("AIRTABLE_BASE_ID")
    table_name = os.getenv("AIRTABLE_TABLE_NAME")
    api_key = os.getenv("AIRTABLE_API_KEY")

    airtable = Airtable(base_id, table_name, api_key)
    records = airtable.get_all()

    vip_ids = []
    for record in records:
        fields = record.get("fields", {})
        telegram_id = fields.get("ID Telegram")
        if telegram_id:
            try:
                vip_ids.append(int(telegram_id))
            except ValueError:
                continue

    return vip_ids
