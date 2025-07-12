from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

keyboard_admin = ReplyKeyboardMarkup(resize_keyboard=True)
keyboard_admin.add("📦 Commandes", "📊 Statistiques")
keyboard_admin.add("❌ Bannir un client", "✅ Réintégrer un client")
keyboard_admin.add("📤 Envoyer un contenu")  # Nouveau bouton