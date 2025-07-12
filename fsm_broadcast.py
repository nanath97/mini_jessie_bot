# fsm_broadcast.py
from aiogram import types
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.dispatcher.filters import Text
from core import bot, dp
import requests
import asyncio
from bott_webhook import keyboard_admin
from config import ADMIN_ID, liens_paiement, BASE_ID, TABLE_NAME, AIRTABLE_API_KEY  # adapte à ton projet

class BroadcastContent(StatesGroup):
    TITLE = State()
    MEDIA = State()
    PRICE = State()
    CONFIRM = State()

@dp.message_handler(lambda m: m.text == "📤 Envoyer un contenu" and m.from_user.id == ADMIN_ID)
async def start_broadcast_content(message: types.Message):
    await BroadcastContent.TITLE.set()
    await message.answer("📝 Quel est le *titre* du contenu à envoyer ?", parse_mode="Markdown")

@dp.message_handler(state=BroadcastContent.TITLE, content_types=types.ContentType.TEXT)
async def process_title_step(message: types.Message, state: FSMContext):
    await state.update_data(title=message.text.strip())
    await BroadcastContent.MEDIA.set()
    await message.answer("📎 Envoie maintenant le *média* (photo, vidéo, document ou audio).", parse_mode="Markdown")

@dp.message_handler(state=BroadcastContent.MEDIA, content_types=[types.ContentType.PHOTO, types.ContentType.VIDEO, types.ContentType.DOCUMENT, types.ContentType.AUDIO])
async def process_media_step(message: types.Message, state: FSMContext):
    content_type = message.content_type
    file_id = (
        message.photo[-1].file_id if content_type == types.ContentType.PHOTO else
        message.video.file_id if content_type == types.ContentType.VIDEO else
        message.document.file_id if content_type == types.ContentType.DOCUMENT else
        message.audio.file_id
    )
    await state.update_data(file_id=file_id, content_type=content_type)
    await BroadcastContent.PRICE.set()
    await message.answer("💶 Quel est le *prix* en euros ? (9, 19, 29...)", parse_mode="Markdown")

@dp.message_handler(state=BroadcastContent.PRICE, content_types=types.ContentType.TEXT)
async def process_price_step(message: types.Message, state: FSMContext):
    price = message.text.strip()
    if price not in liens_paiement:
        return await message.answer("❌ Prix non valide. Utilise : 9, 19, 29...")

    data = await state.get_data()
    await state.update_data(price=price, payment_link=liens_paiement[price])

    recap = (
        f"📦 *Récapitulatif :*\n"
        f"🎬 Titre : {data['title']}\n"
        f"💸 Prix : {price} €\n"
        f"🔗 Lien : {liens_paiement[price]}\n\n"
        f"✅ Confirmer l'envoi à tous les VIP ?"
    )
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True).add("✅ Confirmer", "❌ Annuler")
    await BroadcastContent.CONFIRM.set()
    await message.answer(recap, parse_mode="Markdown", reply_markup=kb)

@dp.message_handler(state=BroadcastContent.CONFIRM)
async def process_confirm_step(message: types.Message, state: FSMContext):
    if message.text == "✅ Confirmer":
        data = await state.get_data()

        # Récupérer les VIP
        try:
            url = f"https://api.airtable.com/v0/{BASE_ID}/{TABLE_NAME.replace(' ', '%20')}"
            params = {"filterByFormula": "{Type acces}='VIP'"}
            headers = {"Authorization": f"Bearer {AIRTABLE_API_KEY}"}
            response = requests.get(url, headers=headers, params=params)
            vip_ids = [int(r["fields"]["ID Telegram"]) for r in response.json().get("records", []) if r["fields"].get("ID Telegram")]
        except Exception as e:
            await message.answer("❌ Erreur Airtable.")
            return await state.finish()

        # Envoi
        sent = 0
        for uid in vip_ids:
            try:
                await bot.send_message(uid, f"🎬 {data['title']}\n💸 {data['price']} €\n👉 {data['payment_link']}")
                if data["content_type"] == types.ContentType.PHOTO:
                    await bot.send_photo(uid, data["file_id"])
                elif data["content_type"] == types.ContentType.VIDEO:
                    await bot.send_video(uid, data["file_id"])
                elif data["content_type"] == types.ContentType.DOCUMENT:
                    await bot.send_document(uid, data["file_id"])
                elif data["content_type"] == types.ContentType.AUDIO:
                    await bot.send_audio(uid, data["file_id"])
                sent += 1
                await asyncio.sleep(0.5)
            except Exception as e:
                print(f"[ERREUR] Envoi échoué à {uid}: {e}")
                continue

        await message.answer(f"✅ Contenu envoyé à {sent} VIP.", reply_markup=keyboard_admin)
    else:
        await message.answer("❌ Envoi annulé.", reply_markup=keyboard_admin)

    await state.finish()

