# offer_trigger.py
import os
import datetime
from ai_state_store import get_state, upsert_state
from payment_links import liens_paiement
from vip_topics import ensure_topic_for_vip
from aiogram import types
from core import DEFAULT_FLOU_IMAGE_FILE_ID

STAFF_GROUP_ID = int(os.getenv("STAFF_GROUP_ID", "0"))

async def trigger_offer(bot, user_id: int, offer_code: str, origin="AI"):
    """
    Déclenche une offre NovaPulse (équivalent /envXX, sans texte).
    """
    state = get_state(user_id)
    if not state:
        return False

    fields = state.get("fields", {})
    offers_sent = int(fields.get("Offers Sent") or 0)

    # Sécurité business
    if offers_sent >= 5:
        return False

    lien = liens_paiement.get(str(offer_code))
    if not lien:
        return False

    # Topic client
    try:
        dummy_user = types.User(id=user_id, is_bot=False, first_name=str(user_id))
        topic_id = await ensure_topic_for_vip(dummy_user)
    except Exception:
        topic_id = None

    caption = (
        f"🔒 *Contenu privé*\n\n"
        f"👉 Débloque ici : {lien}"
    )

    # 1️⃣ Image floutée + lien
    await bot.send_photo(
        chat_id=user_id,
        photo=DEFAULT_FLOU_IMAGE_FILE_ID,
        caption=caption,
        parse_mode="Markdown"
    )

    # 2️⃣ Message complémentaire
    await bot.send_message(
        chat_id=user_id,
        text=f"_💡 Offre {offer_code}€ – disponible maintenant._",
        parse_mode="Markdown"
    )

    # 3️⃣ Update Airtable
    upsert_state(
        user_id,
        {
            "Offers Sent": offers_sent + 1,
            "Last Offer Code": str(offer_code),
            "Last Offer At": datetime.datetime.utcnow().isoformat()
        }
    )

    # 4️⃣ Notif staff (topic)
    if STAFF_GROUP_ID and topic_id:
        try:
            await bot.request(
                "sendMessage",
                {
                    "chat_id": STAFF_GROUP_ID,
                    "message_thread_id": topic_id,
                    "text": (
                        f"💸 *Offre IA envoyée*\n\n"
                        f"👤 Client : `{user_id}`\n"
                        f"💶 Montant : {offer_code} €\n"
                        f"🤖 Origine : {origin}"
                    ),
                    "parse_mode": "Markdown"
                }
            )
        except Exception:
            pass

    return True


upsert_state(
    user_id,
    {
        "Offers Sent": offers_sent + 1,
        "Last Offer Code": str(offer_code),
        "Last Offer At": datetime.datetime.utcnow().isoformat(),
        "Last Offer Step": fields.get("Step Index")
    }
)
