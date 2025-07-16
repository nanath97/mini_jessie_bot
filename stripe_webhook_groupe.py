
from dotenv import load_dotenv
load_dotenv()

from fastapi import APIRouter, Request, HTTPException
import stripe
import os
from datetime import datetime
from bott_webhook import log_to_airtable  # Assure-toi que ce chemin est bon
from aiogram import Bot


stripe.api_key = os.getenv("STRIPE_SECRET_KEY")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET_GROUPE")
BOT_TOKEN = os.getenv("BOT_TOKEN")

bot = Bot(token=BOT_TOKEN)
router = APIRouter()

# Ton mapping des montants vers les contenus groupés
CONTENUS_PAR_MONTANT = {
    9: "Contenu groupé 9 €",
    14: "Contenu groupé 14 €",
    19: "Contenu groupé 19 €",
    # Ajoute d’autres niveaux ici si besoin
}

@router.post("/webhook-groupe")
async def stripe_group_webhook(request: Request):
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")

    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, STRIPE_WEBHOOK_SECRET
        )
    except stripe.error.SignatureVerificationError:
        raise HTTPException(status_code=400, detail="Signature invalide")
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        payment_status = session.get("payment_status")
        amount_total = session.get("amount_total", 0) / 100  # Stripe renvoie en centimes
        email_client = session.get("customer_details", {}).get("email", "").lower()

        if payment_status != "paid":
            print("❌ Paiement non validé")
            return {"status": "ignored"}

        print(f"✅ Paiement groupé reçu : {email_client} - {amount_total} €")

        # Récupérer l’ID Telegram du client dans Airtable (via Email Client)
        from utils.airtable_client import get_telegram_id_by_email  # à créer si pas déjà
        user_id, pseudo = get_telegram_id_by_email(email_client)

        if not user_id:
            print("❌ Email non reconnu dans Airtable")
            return {"status": "email_not_found"}

        # Envoyer le bon contenu
        contenu = CONTENUS_PAR_MONTANT.get(int(amount_total), "Contenu groupé")
        try:
            await bot.send_message(
                chat_id=int(user_id),
                text=f"✅ Merci pour ton paiement ! Voici ton contenu :\n\n{contenu}"
            )
        except Exception as e:
            print(f"Erreur envoi message Telegram : {e}")

        # Log dans Airtable
        log_to_airtable(
            pseudo=pseudo,
            user_id=user_id,
            type_acces="groupé",
            montant=amount_total,
            contenu=contenu,
            email_client=email_client
        )

    return {"status": "success"}
