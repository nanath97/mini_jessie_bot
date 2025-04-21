from fastapi import FastAPI
from aiogram import Bot, Dispatcher
import os
from dotenv import load_dotenv
from bott_webhook import register_handlers

# Charger les variables d'environnement
load_dotenv()

# Initialiser le bot et le dispatcher
TOKEN = os.getenv('BOT_TOKEN')
bot = Bot(token=TOKEN)
dp = Dispatcher(bot=bot)

# Créer l'application FastAPI
app = FastAPI()

# Enregistrer les handlers personnalisés
register_handlers(dp)