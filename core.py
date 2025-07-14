from aiogram import Bot, Dispatcher
from aiogram.contrib.fsm_storage.memory import MemoryStorage
import os
from dotenv import load_dotenv
from middlewares.payment_filter import PaymentFilterMiddleware

# ✅ Charger les variables d'environnement (.env)
load_dotenv()

# ✅ Récupération du token du bot
BOT_TOKEN = os.getenv("BOT_TOKEN")

# ✅ Initialisation du bot
bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()  # FSM MemoryStorage

# ✅ Dispatcher avec support des états
dp = Dispatcher(bot, storage=storage)

# ✅ Liste des utilisateurs autorisés pour le middleware
authorized_users = set()

# ✅ Activation du middleware de filtre de paiement
dp.middleware.setup(PaymentFilterMiddleware(authorized_users))

# ✅ Pour éviter l’erreur "dp non défini" ailleurs
__all__ = ["bot", "dp", "storage", "authorized_users"]
