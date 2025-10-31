from aiogram import Bot, Dispatcher
import os
from dotenv import load_dotenv
from middlewares.payment_filter import PaymentFilterMiddleware




load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
bot = Bot(token=BOT_TOKEN)
bot.set_current(bot)
dp = Dispatcher(bot)
# ===== AJOUT NOVA PROTECTION PAIEMENT (NE PAS TOUCHER) =====
authorized_users = set()
# ===== Activation du middleware =====
dp.middleware.setup(PaymentFilterMiddleware(authorized_users))









from datetime import datetime
import requests

AIRTABLE_API_KEY = os.getenv("AIRTABLE_API_KEY")
BASE_ID = os.getenv("AIRTABLE_BASE_ID")
TABLE_NAME = os.getenv("AIRTABLE_TABLE_NAME", "Paiements")

def log_to_airtable(pseudo, user_id, type_acces, montant, contenu="Paiement Telegram", email="vinteo.ac@gmail.com"):
    if not type_acces:
        type_acces = "Paiement"

    url = f"https://api.airtable.com/v0/{BASE_ID}/{TABLE_NAME.replace(' ', '%20')}"
    headers = {
        "Authorization": f"Bearer {AIRTABLE_API_KEY}",
        "Content-Type": "application/json"
    }

    now = datetime.now()

    fields = {
        "Pseudo Telegram": pseudo or "-",
        "ID Telegram": str(user_id),
        "Type acces": str(type_acces),
        "Montant": float(montant),
        "Contenu": contenu,
        "Email": email,
        "Date": now.isoformat(),
        "Mois": now.strftime("%Y-%m")
    }

    data = {"fields": fields}
    response = requests.post(url, json=data, headers=headers)
    if response.status_code != 200:
        print(f"❌ Erreur enregistrement Airtable : {response.status_code} — {response.text}")
