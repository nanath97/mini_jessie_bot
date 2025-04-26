from core import bot, dp
from aiogram import types
import os
from datetime import datetime

# ADMIN ID
ADMIN_ID = 7334072965

# Liste des prix autorisés
prix_list = [9, 14, 19, 24, 29, 34, 39, 44, 49, 59, 69, 79, 89, 99]

# Liste blanche des liens autorisés
WHITELIST_LINKS = [
    "https://novapulseonline.wixsite.com/",
    "https://buy.stripe.com/",
    "https://t.me/mini_jessie_bot?startpaid"
]

# Fonction de détection de lien non autorisé
def lien_non_autorise(text):
    return any(part.startswith("http") and not any(allowed in part for allowed in WHITELIST_LINKS) for part in text.split())

# Création du clavier
keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
keyboard.add(
    types.KeyboardButton("🔞Voir la vidéo du jour"),
    types.KeyboardButton("👀Je suis un voyeur"),
    types.KeyboardButton("✨Discuter en tant que VIP")
)

# Commande /start
@dp.message_handler(commands=["start"])
async def handle_start(message: types.Message):
    param = message.get_args()

    if param.startswith("paid") and param[4:].isdigit():
        montant = int(param[4:])
        if montant in prix_list:
            await bot.send_message(message.chat.id, f"✅ Merci pour ton paiement de {montant}€ 💖")
            await bot.send_message(ADMIN_ID, f"💰 Nouveau paiement de {montant}€ de {message.from_user.username or message.from_user.first_name}.")
            return

    if param in ["vipaccess", "vipaccess123"]:
        await bot.send_message(message.chat.id, "✨ Bienvenue dans le VIP !")
        await bot.send_message(ADMIN_ID, f"🌟 Nouveau VIP : {message.from_user.username or message.from_user.first_name}.")
        return

    await bot.send_message(message.chat.id, f"👋 Salut {message.from_user.first_name or 'toi'}, que veux-tu faire ?", reply_markup=keyboard)

# Gestion des boutons
@dp.message_handler(lambda message: message.text == "🔞Voir la vidéo du jour")
async def voir_video(message: types.Message):
    await bot.send_message(message.chat.id, "🎥 Voici ta vidéo du jour : https://buy.stripe.com/fZeg328Th4K67zW9AA")

@dp.message_handler(lambda message: message.text == "✨Discuter en tant que VIP")
async def discuter_vip(message: types.Message):
    await bot.send_message(message.chat.id, "🚀 Deviens VIP ici : https://buy.stripe.com/4gwg32fhF4K62fCdQR")

@dp.message_handler(lambda message: message.text == "👀Je suis un voyeur")
async def je_suis_voyeur(message: types.Message):
    keyboard_confirm = types.ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard_confirm.add(
        types.KeyboardButton("✅ Oui je confirme (bannir)"),
        types.KeyboardButton("🚀 Non, je veux rejoindre le VIP")
    )
    await bot.send_message(message.chat.id, "Confirme ton choix :", reply_markup=keyboard_confirm)

@dp.message_handler(lambda message: message.text == "✅ Oui je confirme (bannir)")
async def confirmer_voyeur(message: types.Message):
    await bot.send_message(message.chat.id, "🛑 Tu restes simple spectateur.")

@dp.message_handler(lambda message: message.text == "🚀 Non, je veux rejoindre le VIP")
async def rejoindre_vip(message: types.Message):
    await bot.send_message(message.chat.id, "🚀 Super ! Voici ton lien VIP : https://buy.stripe.com/4gwg32fhF4K62fCdQR", reply_markup=keyboard)

# Suppression des liens interdits
@dp.message_handler(lambda message: message.text and "http" in message.text)
async def supprimer_liens_interdits(message: types.Message):
    if lien_non_autorise(message.text):
        try:
            await bot.delete_message(chat_id=message.chat.id, message_id=message.message_id)
            await bot.send_message(chat_id=message.chat.id, text="🚫 Les liens extérieurs sont interdits.")
        except Exception as e:
            print(f"Erreur suppression lien externe : {e}")

# Relay client -> admin
@dp.message_handler(lambda message: message.from_user.id != ADMIN_ID)
async def relay_from_client(message: types.Message):
    try:
        if message.text:
            await bot.forward_message(chat_id=ADMIN_ID, from_chat_id=message.chat.id, message_id=message.message_id)

        elif message.photo:
            file = await bot.get_file(message.photo[-1].file_id)
            file_path = file.file_path
            temp_file = f"/tmp/{file_path.split('/')[-1]}"
            await bot.download_file(file_path, temp_file)
            with open(temp_file, 'rb') as photo:
                await bot.send_photo(chat_id=ADMIN_ID, photo=photo, caption=message.caption if message.caption else "")
            os.remove(temp_file)

        elif message.video:
            file = await bot.get_file(message.video.file_id)
            file_path = file.file_path
            temp_file = f"/tmp/{file_path.split('/')[-1]}"
            await bot.download_file(file_path, temp_file)
            with open(temp_file, 'rb') as video:
                await bot.send_video(chat_id=ADMIN_ID, video=video, caption=message.caption if message.caption else "")
            os.remove(temp_file)

        elif message.document:
            file = await bot.get_file(message.document.file_id)
            file_path = file.file_path
            temp_file = f"/tmp/{file_path.split('/')[-1]}"
            await bot.download_file(file_path, temp_file)
            with open(temp_file, 'rb') as doc:
                await bot.send_document(chat_id=ADMIN_ID, document=doc, caption=message.caption if message.caption else "")
            os.remove(temp_file)

        elif message.voice:
            file = await bot.get_file(message.voice.file_id)
            file_path = file.file_path
            temp_file = f"/tmp/{file_path.split('/')[-1]}"
            await bot.download_file(file_path, temp_file)
            with open(temp_file, 'rb') as voice:
                await bot.send_voice(chat_id=ADMIN_ID, voice=voice)
            os.remove(temp_file)

        elif message.audio:
            file = await bot.get_file(message.audio.file_id)
            file_path = file.file_path
            temp_file = f"/tmp/{file_path.split('/')[-1]}"
            await bot.download_file(file_path, temp_file)
            with open(temp_file, 'rb') as audio:
                await bot.send_audio(chat_id=ADMIN_ID, audio=audio, caption=message.caption if message.caption else "")
            os.remove(temp_file)

        else:
            await bot.send_message(chat_id=ADMIN_ID, text="📂 Un type de fichier non supporté a été reçu.")

    except Exception as e:
        await bot.send_message(chat_id=ADMIN_ID, text=f"❗Erreur lors du relay client -> admin.\n{e}")
        print(f"Erreur relay client -> admin : {e}")
