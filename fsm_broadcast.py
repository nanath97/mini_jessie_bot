# fsm_broadcast.py
import os
import asyncio
import requests
from aiogram import types, Dispatcher
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from core import bot, dp, authorized_users
from keyboards import keyboard_admin


# Configuration (reprend les valeurs que tu utilises déjà dans ton projet)
ADMIN_ID = os.getenv("ADMIN_ID")
BASE_ID = os.getenv("BASE_ID")
TABLE_NAME = os.getenv("TABLE_NAME")
AIRTABLE_API_KEY = os.getenv("AIRTABLE_API_KEY")

liens_paiement = {
    "9": "https://stripe.com/lien_9",
    "19": "https://stripe.com/lien_19",
    "29": "https://stripe.com/lien_29",
    "39": "https://stripe.com/lien_39",
}

class BroadcastContent(StatesGroup):
    TITLE = State()
    MEDIA = State()
    PRICE = State()
    CONFIRM = State()

@dp.message_handler(lambda m: m.text == "📤 Envoyer un contenu" and m.from_user.id == ADMIN_ID)
async def start_broadcast_content(message: types.Message):
    """Démarre le processus FSM pour envoyer un contenu payant à tous les VIP."""
    await BroadcastContent.TITLE.set()
    await message.answer("📝 Quel est le *titre* du contenu à envoyer ?",
                         parse_mode="Markdown")

@dp.message_handler(state=BroadcastContent.TITLE, content_types=types.ContentType.TEXT)
async def process_title_step(message: types.Message, state: FSMContext):
    """Étape 1 : titre du contenu."""
    # Enregistre le titre saisi et passe à l'étape suivante (média).
    await state.update_data(title=message.text.strip())
    await BroadcastContent.MEDIA.set()
    await message.answer("📎 Envoie maintenant le *média* (photo, vidéo, document ou audio).",
                         parse_mode="Markdown")

@dp.message_handler(state=BroadcastContent.MEDIA, content_types=[types.ContentType.PHOTO,
                                                                 types.ContentType.VIDEO,
                                                                 types.ContentType.DOCUMENT,
                                                                 types.ContentType.AUDIO])
async def process_media_step(message: types.Message, state: FSMContext):
    """Étape 2 : réception du média."""
    # Récupère le file_id du média envoyé, quel que soit son type
    content_type = message.content_type
    if content_type == types.ContentType.PHOTO:
        file_id = message.photo[-1].file_id  # dernière photo = meilleure qualité
    elif content_type == types.ContentType.VIDEO:
        file_id = message.video.file_id
    elif content_type == types.ContentType.DOCUMENT:
        file_id = message.document.file_id
    else:  # AUDIO
        file_id = message.audio.file_id
    # Stocke le file_id et le type de contenu, puis passe à l'étape suivante (prix).
    await state.update_data(file_id=file_id, content_type=content_type)
    await BroadcastContent.PRICE.set()
    await message.answer("💶 Quel est le *prix* en euros ? (9, 19, 29, ...)",
                         parse_mode="Markdown")

@dp.message_handler(state=BroadcastContent.PRICE, content_types=types.ContentType.TEXT)
async def process_price_step(message: types.Message, state: FSMContext):
    """Étape 3 : choix du prix et récupération du lien de paiement."""
    price = message.text.strip()
    # Vérifie que le prix correspond à un lien de paiement existant.
    if price not in liens_paiement:
        return await message.answer("❌ Prix non valide. Utilise : 9, 19, 29...")

    # Enregistre le prix et le lien de paiement correspondant.
    await state.update_data(price=price, payment_link=liens_paiement[price])
    data = await state.get_data()  # on récupère aussi le titre pour le récap

    # Prépare le récapitulatif à confirmer
    recap = (
        f"📦 *Récapitulatif :*\n"
        f"🎬 Titre : {data['title']}\n"
        f"💸 Prix : {price} €\n"
        f"🔗 Lien : {liens_paiement[price]}\n\n"
        f"✅ *Confirmer l'envoi à tous les VIP ?*"
    )
    # Clavier de confirmation (oui/non)
    kb_confirm = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb_confirm.add("✅ Confirmer", "❌ Annuler")
    # Passe à l'état de confirmation et envoie le message récap avec les boutons.
    await BroadcastContent.CONFIRM.set()
    await message.answer(recap, parse_mode="Markdown", reply_markup=kb_confirm)

@dp.message_handler(state=BroadcastContent.CONFIRM)
async def process_confirm_step(message: types.Message, state: FSMContext):
    """Étape 4 : confirmation ou annulation, puis envoi du contenu aux VIP (étape 5)."""

    if message.text == "✅ Confirmer":
        # L'admin confirme l’envoi du contenu à tous les VIP.
        data = await state.get_data()
        try:
            # Récupère la liste des IDs Telegram des VIP depuis Airtable
            url = f"https://api.airtable.com/v0/{BASE_ID}/{TABLE_NAME.replace(' ', '%20')}"
            params = {"filterByFormula": "{Type acces}='VIP'"}
            headers = {"Authorization": f"Bearer {AIRTABLE_API_KEY}"}
            response = requests.get(url, headers=headers, params=params)
            response.raise_for_status()
            records = response.json().get("records", [])
            vip_ids = [int(rec["fields"]["ID Telegram"]) for rec in records if rec["fields"].get("ID Telegram")]
        except Exception as e:
            # En cas d'erreur (réseau, parse JSON...), on avertit et on termine le FSM.
            await message.answer("❌ Erreur Airtable. Impossible de récupérer la liste des VIP.",
                                 reply_markup=keyboard_admin)
            await state.finish()
            return

        # Envoi du contenu à chaque VIP
        sent_count = 0
        for uid in vip_ids:
            try:
                # Envoie le message texte (titre, prix, lien)
                await bot.send_message(uid,
                                       f"🎬 {data['title']}\n"
                                       f"💸 {data['price']} €\n"
                                       f"👉 {data['payment_link']}")
                # Envoie le média selon son type (sans légende supplémentaire pour ne pas répéter le lien)
                if data["content_type"] == types.ContentType.PHOTO:
                    await bot.send_photo(uid, data["file_id"])
                elif data["content_type"] == types.ContentType.VIDEO:
                    await bot.send_video(uid, data["file_id"])
                elif data["content_type"] == types.ContentType.DOCUMENT:
                    await bot.send_document(uid, data["file_id"])
                elif data["content_type"] == types.ContentType.AUDIO:
                    await bot.send_audio(uid, data["file_id"])
                sent_count += 1
                await asyncio.sleep(0.5)  # petite pause pour éviter un flood
            except Exception as e:
                # En cas d’échec d’envoi à un utilisateur (ex: utilisateur bloqué), on log et on continue.
                print(f"[ERREUR] Échec d'envoi au VIP {uid} : {e}")
                continue

        # Notification de fin d’envoi à l’admin avec le clavier admin restauré.
        await message.answer(f"✅ Contenu envoyé à {sent_count} VIP.", reply_markup=keyboard_admin)

    else:
        # L'admin a envoyé autre chose que "Confirmer" (ex: "Annuler" ou autre) → on annule.
        await message.answer("❌ Envoi annulé.", reply_markup=keyboard_admin)

    # Fin du FSM (on sort de l'état quel que soit le cas).
    await state.finish()
