from aiogram import Bot, Dispatcher, executor, types

API_TOKEN = '7623543469:AAFWp224VKWuyf32eY7SqsF6m4en3EF9nNU'  # Remplace par ton token BotFather

bot = Bot(token=API_TOKEN)
dp = Dispatcher(bot)

# Commande de démarrage
@dp.message_handler(commands=['start'])
async def send_welcome(message: types.Message):
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
    buttons = ["Discuter en tant que VIP", "Voir le contenu du jour", "Juste discuter"]
    keyboard.add(*buttons)

    await message.answer("Salut mon coeur ! Que veux-tu faire ?", reply_markup=keyboard)

# Option 1 : Discuter en tant que VIP
@dp.message_handler(lambda message: message.text == "Discuter en tant que VIP")
async def show_preview(message: types.Message):
    await message.answer("Nous allons faire connaissance, je t'offrirai des cadeaux surprises et je vais te montrer mon corps sous toutes ses formes! Tu pourras les débloquer après achat. Clique ici : https://t.me/+Kk86-FYp4S05OWQ0")

# Option 2 : Voir le contenu du jour
@dp.message_handler(lambda message: message.text == "Voir le contenu du jour")
async def offer(message: types.Message):
    await message.answer("Aujourd’hui, tu peux débloquer 1 vidéo de moi me doigtant comme une coquine dans ma salle de bain, plus 1 figurine digitale de ma miniature pour seulement 39€. Offre valable pendant 1 heure. Clique ici : https://t.me/+54dzzTNvQfYxMDQ0")

# Option 3 : Juste discuter
@dp.message_handler(lambda message: message.text == "Juste discuter")
async def chat(message: types.Message):
    await message.answer("Tu peux m’écrire ici directement. Mais sache que mes contenus exclusifs sont réservés aux abonnés ! Et ce n'est pas sûr que je te réponde de suite...")

# Lancement du bot
if __name__ == '__main__':
    executor.start_polling(dp, skip_updates=True)
