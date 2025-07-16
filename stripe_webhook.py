# stripe_webhook.py

from fastapi import APIRouter, Request, Header
import stripe
import os
import requests
from datetime import datetime
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from core import bot
from bott_webhook import log_to_airtable, paiements_recents

router = APIRouter()

stripe.api_key = os.getenv("STRIPE_SECRET_KEY")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET")
BASE_ID = os.getenv("AIRTABLE_BASE_ID")
TABLE_NAME = os.getenv("AIRTABLE_TABLE_NAME")
AIRTABLE_API_KEY = os.getenv("AIRTABLE_API_KEY")
ADMIN_ID = int(os.getenv("ADMIN_ID"))  # Ton ID Telegram

# Lien de paiement groupé TEST (1€)
LIEN_GROUPE_TEST = "https://buy.stripe.com/9B67sK9cV2ET4cdd9X7AI0h"

@router.get("/stripe/test")
async def test_stripe_route():
    return {"status": "ok"}

@router.post("/stripe/webhook")
async def stripe_webhook(request: Request, stripe_signature: str = Header(None)):
    payload = await request.body()

    try:
        event = stripe.Webhook.construct_event(
            payload, stripe_signature, STRIPE_WEBHOOK_SECRET
        )
    except Exception as e:
        print(f"❌ Webhook Stripe invalide : {e}")
        return {"status": "invalid"}

    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]

        amount_raw = session.get("amount_total")
        if amount_raw is None:
            print("❌ Montant non trouvé dans la session Stripe.")
            return {"status": "missing_amount"}

        montant = int(amount_raw / 100)
        email_client = session.get("customer_details", {}).get("email", "inconnu")

        url_check = session.get("metadata", {}).get("payment_link", "")
        if url_check == "":
            url_check = session.get("client_reference_id", "") or session.get("url", "")

        print(f"🔍 Vérification du lien de paiement : {url_check}")

        if LIEN_GROUPE_TEST in url_check:
            print("🎯 Paiement groupé détecté")

            airtable_url = f"https://api.airtable.com/v0/{BASE_ID}/{TABLE_NAME}"
            headers = {"Authorization": f"Bearer {AIRTABLE_API_KEY}"}
            params = {"filterByFormula": f'{{Email}}="{email_client}"'}

            try:
                r = requests.get(airtable_url, headers=headers, params=params)
                r.raise_for_status()
                data = r.json()

                if data["records"]:
                    id_field = data["records"][0]["fields"].get("ID Telegram")
                    pseudo = data["records"][0]["fields"].get("Pseudo Telegram", "-")

                    if id_field is not None:
                        user_id = int(id_field)
                        print(f"✅ Email trouvé dans Airtable : {email_client} → ID = {user_id}")
                    else:
                        user_id = None
                        print(f"⚠️ Email trouvé dans Airtable mais ID Telegram manquant : {email_client}")
                else:
                    user_id = None
                    pseudo = "-"
                    print(f"⚠️ Email non trouvé dans Airtable : {email_client}")

                log_to_airtable(
                    pseudo=pseudo,
                    user_id=user_id or "inconnu",
                    type_acces="groupé",
                    montant=montant,
                    contenu="Contenu groupé Telegram",
                    email=email_client
                )

                if user_id:
                    bouton = InlineKeyboardMarkup().add(
                        InlineKeyboardButton("📥 Recevoir mon contenu", callback_data="recevoir_contenu_groupe")
                    )
                    await bot.send_message(
                        user_id,
                        "Merci pour ton paiement ! Clique ici pour recevoir ton contenu 👇",
                        reply_markup=bouton
                    )
                else:
                    await bot.send_message(
                        ADMIN_ID,
                        f"⚠️ Un client a payé {montant}€ (groupé) mais son email n’a pas été trouvé dans Airtable : {email_client}"
                    )

            except Exception as e:
                print(f"❌ Erreur Airtable lors de la recherche email client : {e}")
        else:
            # Paiement individuel
            paiements_recents[montant].append(datetime.now())
            print(f"✅ Paiement individuel : {montant}€ enregistré à {datetime.now().isoformat()}")

    return {"status": "ok"}
