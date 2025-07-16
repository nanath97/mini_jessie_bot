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

# Chargement de l'ID admin Telegram depuis les variables d'environnement
admin_id_env = os.getenv("ADMIN_ID") or os.getenv("ADMIN_TELEGRAM_ID")
ADMIN_ID = int(admin_id_env) if admin_id_env and admin_id_env.isdigit() else 0
if ADMIN_ID == 0:
    print("❌ ADMIN_ID non configuré ou invalide dans .env")

# Lien de paiement groupé (exemple de lien Stripe de test à 1€)
LIEN_GROUPE_TEST = "https://buy.stripe.com/9B67sK9cV2ET4cdd9X7AI0h"

@router.get("/stripe/test")
async def test_stripe_route():
    return {"status": "ok"}

@router.post("/stripe/webhook")
async def stripe_webhook(request: Request, stripe_signature: str = Header(None)):
    payload = await request.body()
    try:
        # Construction sécurisée de l'événement à partir de la payload Stripe
        event = stripe.Webhook.construct_event(
            payload, stripe_signature, STRIPE_WEBHOOK_SECRET
        )
    except Exception as e:
        print(f"❌ Webhook Stripe invalide : {e}")
        return {"status": "invalid"}

    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]

        # Récupération du montant total payé (en cents) et conversion en euros
        amount_raw = session.get("amount_total")
        if amount_raw is None:
            print("❌ Montant non trouvé dans la session Stripe.")
            return {"status": "missing_amount"}
        montant = int(amount_raw / 100)

        # Récupération de l’email du client depuis la session Stripe
        email_client = session.get("customer_details", {}).get("email", "inconnu")

        # Vérification de l’URL ou du méta-donnée pour identifier le lien de paiement
        url_check = session.get("metadata", {}).get("payment_link", "")
        if url_check == "":
            url_check = session.get("client_reference_id", "") or session.get("url", "")
        print(f"🔍 Vérification du lien de paiement : {url_check}")

        if LIEN_GROUPE_TEST in url_check:
            print("🎯 Paiement groupé détecté")

            # Préparation de la requête vers Airtable pour retrouver le client par email
            airtable_url = f"https://api.airtable.com/v0/{BASE_ID}/{TABLE_NAME}"
            headers = {"Authorization": f"Bearer {AIRTABLE_API_KEY}"}
            params = {"filterByFormula": f'{{Email}}="{email_client}"'}

            try:
                r = requests.get(airtable_url, headers=headers, params=params)
                r.raise_for_status()
                data = r.json()

                user_id = None
                pseudo = "-"

                if data["records"]:
                    # Email trouvé dans la base Airtable
                    fields = data["records"][0]["fields"]
                    print("🔎 Champs trouvés dans Airtable :", fields)
                    id_field = fields.get("ID Telegram")
                    pseudo = fields.get("Pseudo Telegram", "-")
                    if id_field is not None and str(id_field).isdigit():
                        # ID Telegram valide récupéré
                        user_id = int(id_field)
                        print(f"✅ Email trouvé dans Airtable : {email_client} → ID = {user_id}")
                    else:
                        # Email existant mais ID Telegram manquant ou invalide
                        print(f"⚠️ Email trouvé mais ID Telegram invalide ou vide : {email_client} (valeur = {id_field})")
                else:
                    # Aucun enregistrement Airtable pour cet email
                    print(f"⚠️ Email non trouvé dans Airtable : {email_client}")

                # Journalisation du paiement dans Airtable (pseudo, ID ou "inconnu", etc.)
                log_to_airtable(
                    pseudo=pseudo,
                    user_id=user_id or "inconnu",
                    type_acces="groupé",
                    montant=montant,
                    contenu="Contenu groupé Telegram",
                    email=email_client
                )

                # Envoi du contenu au client si l'ID Telegram est disponible
                if user_id:
                    bouton = InlineKeyboardMarkup().add(
                        InlineKeyboardButton("📥 Recevoir mon contenu", callback_data="recevoir_contenu_groupe")
                    )
                    await bot.send_message(
                        user_id,
                        "Merci pour ton paiement ! Clique ici pour recevoir ton contenu 👇",
                        reply_markup=bouton
                    )
                # Alerte l’admin si l’ID Telegram est invalide ou absent malgré l’email trouvé
                elif data["records"]:
                    if ADMIN_ID:
                        await bot.send_message(
                            ADMIN_ID,
                            f"⚠️ Un client a payé {montant}€ (groupé) mais son ID Telegram est invalide ou manquant dans Airtable (email : {email_client})."
                        )
                    else:
                        print(f"⚠️ [Alerte Admin] Paiement groupé de {montant}€ reçu, email {email_client} trouvé mais ID Telegram invalide/introuvable. ADMIN_ID non configuré.")
                # Alerte l’admin si l’email du client n’existe pas du tout dans Airtable
                else:
                    if ADMIN_ID:
                        await bot.send_message(
                            ADMIN_ID,
                            f"⚠️ Un client a payé {montant}€ (groupé) mais son email {email_client} est introuvable dans Airtable."
                        )
                    else:
                        print(f"⚠️ [Alerte Admin] Paiement groupé de {montant}€ reçu, email {email_client} introuvable dans Airtable. ADMIN_ID non configuré.")
            except Exception as e:
                # Gestion d’erreur de la requête Airtable (on log l’erreur sans interrompre le flux)
                print(f"❌ Erreur Airtable lors de la recherche email client : {e}")
        else:
            # Paiement individuel (la structure existante est conservée)
            paiements_recents[montant].append(datetime.now())
            print(f"✅ Paiement individuel : {montant}€ enregistré à {datetime.now().isoformat()}")

    return {"status": "ok"}
