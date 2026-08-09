# stripe_webhook.py

from fastapi import APIRouter, Request, Header
import stripe
import os
import requests
from datetime import datetime
from bott_webhook import authorized_admin_ids  # adapte le nom exact du fichier
from core import bot



router = APIRouter()

stripe.api_key = os.getenv("STRIPE_SECRET_KEY")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET")

AIRTABLE_API_KEY = os.getenv("AIRTABLE_API_KEY")
BASE_ID = os.getenv("BASE_ID")
PAYMENT_LINKS_TABLE = "Payment Links"


def mark_payment_link_as_paid_by_session(checkout_session_id: str, buyer_fields: dict = None):
    """
    Met à jour dans Airtable la ligne correspondant au Checkout Session ID.
    """
    try:
        url = f"https://api.airtable.com/v0/{BASE_ID}/{PAYMENT_LINKS_TABLE.replace(' ', '%20')}"
        headers = {
            "Authorization": f"Bearer {AIRTABLE_API_KEY}",
            "Content-Type": "application/json"
        }

        formula = f"{{Checkout Session ID}}='{checkout_session_id}'"

        # 🔎 DEBUG CRITIQUE
        print("========== STRIPE WEBHOOK DEBUG ==========")
        print("BASE_ID =", BASE_ID)
        print("AIRTABLE TABLE =", PAYMENT_LINKS_TABLE)
        print("CHECKOUT_SESSION_ID =", checkout_session_id)
        print("FORMULA =", formula)
        print("URL =", url)
        print("==========================================")

        resp = requests.get(url, headers=headers, params={"filterByFormula": formula})
        print("AIRTABLE RAW RESPONSE =", resp.text)

        records = resp.json().get("records", [])
        if not records:
            print(f"[AIRTABLE] Aucun record trouvé pour session_id={checkout_session_id}")
            return None

        record_id = records[0]["id"]
        patch_url = f"{url}/{record_id}"
        invoice_number = f"NP-{datetime.utcnow().strftime('%Y%m%d-%H%M%S')}"

        airtable_fields = {
            "Status": "Paid",
            "Paid At": datetime.utcnow().isoformat(),
            "Invoice Number": invoice_number
        }

        if buyer_fields:
            airtable_fields.update(buyer_fields)

        update_resp = requests.patch(
            patch_url,
            headers=headers,
            json={"fields": airtable_fields}
        )

        print("PATCH RESPONSE =", update_resp.text)

        if update_resp.status_code not in (200, 201):
            print(f"[AIRTABLE] Erreur update Paid : {update_resp.text}")
            return None

        print(f"[AIRTABLE] session_id={checkout_session_id} marqué Paid")
        return record_id

    except Exception as e:
        print(f"[AIRTABLE] Exception update Paid : {e}")
        return None


@router.post("/stripe/webhook")
async def stripe_webhook(request: Request, stripe_signature: str = Header(None)):
    payload = await request.body()

    # 1) Vérification signature Stripe (sécurité)
    try:
        event = stripe.Webhook.construct_event(
            payload=payload,
            sig_header=stripe_signature,
            secret=STRIPE_WEBHOOK_SECRET
        )
    except Exception as e:
        print(f"❌ Webhook Stripe invalide : {e}")
        return {"status": "invalid"}

    # 2) Traitement event
    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]

        checkout_session_id = session["id"]
        montant_cents = session["amount_total"] or 0
        metadata = session["metadata"] or {}
        customer_details = session["customer_details"] if "customer_details" in session else {}
        address = customer_details["address"] if "address" in customer_details else {}

        custom_fields = session["custom_fields"] if "custom_fields" in session else []

        buyer_company_name = ""
        buyer_siret = ""

        for field in custom_fields:
            key = field["key"] if "key" in field else ""

            text_data = field["text"] if "text" in field else {}
            value = text_data["value"] if "value" in text_data else ""

            if key == "buyer_company_name":
                buyer_company_name = value

            if key == "buyer_siret":
                buyer_siret = value

        tax_ids = customer_details["tax_ids"] if "tax_ids" in customer_details else []
        buyer_vat = ""

        if tax_ids:
            first_tax_id = tax_ids[0]
            buyer_vat = first_tax_id["value"] if "value" in first_tax_id else ""

        buyer_type = "Entreprise" if buyer_company_name or buyer_siret or buyer_vat else "Particulier"
        payment_method_id = ""

        try:
            payment_intent_id = session["payment_intent"] if "payment_intent" in session else None

            if payment_intent_id:
                payment_intent = stripe.PaymentIntent.retrieve(payment_intent_id)

                payment_method_id = (
                    payment_intent["payment_method"]
                    if "payment_method" in payment_intent
                    else ""
                )

                print("💳 STRIPE PAYMENT METHOD ID =", payment_method_id)

        except Exception as e:
            print("❌ Erreur récupération PaymentMethod :", e)
        buyer_fields = {

            "Buyer Name": customer_details["name"] if "name" in customer_details else "",
            "Buyer Email": customer_details["email"] if "email" in customer_details else "",
            "Buyer Phone": customer_details["phone"] if "phone" in customer_details else "",
            "Buyer Address Line 1": address["line1"] if "line1" in address else "",
            "Buyer Address Line 2": address["line2"] if "line2" in address else "",
            "Buyer Postal Code": address["postal_code"] if "postal_code" in address else "",
            "Buyer City": address["city"] if "city" in address else "",
            "Buyer Country": address["country"] if "country" in address else "",
            "Buyer Company Name": buyer_company_name,
            "Buyer SIRET": buyer_siret,
            "Buyer VAT": buyer_vat,
            "Buyer Type": buyer_type,
            "Stripe Customer ID": session["customer"] if "customer" in session else "",
            "Stripe Invoice ID": session["invoice"] if "invoice" in session else "",
            "Stripe Payment Intent ID": session["payment_intent"] if "payment_intent" in session else "",
            "Stripe Payment Method ID": payment_method_id,
        }

        client_key = metadata["client_key"] if "client_key" in metadata else None
        content_id = metadata["content_id"] if "content_id" in metadata else None
        channel = metadata["channel"] if "channel" in metadata else None
        seller_slug = metadata["seller_slug"] if "seller_slug" in metadata else None
        client_username = metadata["username"] if "username" in metadata else client_key or "client"

        montant_euros = round(montant_cents / 100, 2)

        print(
            f"✅ Stripe paid: session={checkout_session_id} amount={montant_cents} "
            f"client={client_key} content={content_id} channel={channel} seller={seller_slug}"
        )

        # 3) Update Airtable
        mark_payment_link_as_paid_by_session(checkout_session_id, buyer_fields)

        # ============================================================
        # 🔔 NOUVEAU : NOTIFICATIONS POST-PAIEMENT
        # ============================================================

        # 3.1 Confirmation client → PWA
        try:
            BRIDGE_API_URL = os.getenv("BRIDGE_API_URL")
            if client_key and BRIDGE_API_URL:
                resp = requests.post(
                    f"{BRIDGE_API_URL}/pwa/send-admin-message",
                    json={
                        "email": client_key,
                        "sellerSlug": seller_slug,
                        "text": (
                            f"✅ Merci pour votre paiement de {montant_euros} € ! "
                            f"Votre facture vous sera transmise directement par mail.\n\n"
                            f"❗️Si vous avez le moindre souci avec votre commande, contactez-nous directement ici"
                        ),
                    },
                    timeout=5,
                )
                print(f"📩 Confirmation client envoyée PWA: {resp.status_code}")
        except Exception as e:
            print(f"❌ Erreur confirmation client PWA: {e}")
            print(f"📩 Confirmation client envoyée PWA: {resp.status_code} {resp.text}")

        # 3.2 Notification admins → Telegram
        try:
            for adm in authorized_admin_ids:
                try:
                    await bot.send_message(
                        adm,
                        f"💰 Nouveau paiement de {montant_euros} € de {client_username}."
                    )
                except Exception as e:
                    print(f"[ADMIN_NOTIFY_ERROR] {e}")
        except Exception as e:
            print(f"❌ Erreur boucle admins: {e}")

                # 3.3 Notification structurée → Topic staff (PWA email-based)
        topic_id = None
        try:
            url_clients = f"https://api.airtable.com/v0/{BASE_ID}/PWA%20Clients"
            headers = {
                "Authorization": f"Bearer {AIRTABLE_API_KEY}",
                "Content-Type": "application/json"
            }

            formula = f"AND({{email}}='{client_key}', {{seller_slug}}='{seller_slug}')"
            resp = requests.get(url_clients, headers=headers, params={"filterByFormula": formula})
            records = resp.json().get("records", [])

            if records:
                topic_id = records[0]["fields"].get("topic_id")

            print(f"📌 Topic lookup Airtable: topic_id={topic_id}")

        except Exception as e:
            print(f"[TOPIC_LOOKUP_ERROR] {e}")

        if topic_id:
            try:
                await bot.request(
                    "sendMessage",
                    {
                        "chat_id": int(os.getenv("STAFF_GROUP_ID", "0")),
                        "message_thread_id": int(topic_id),
                        "text": (
                            f"💰 *Nouveau paiement*\n\n"
                            f"👤 Client : {client_key}\n"
                            f"💶 Montant : {montant_euros} €\n"
                            f"📊 Paiement enregistré dans ton Dashboard.\n"
                            f"📅 Planifier le RDV : https://calendar.google.com/calendar/u/0/r"
                        ),
                        "parse_mode": "Markdown"
                    }
                )
            except Exception as e:
                print(f"[STAFF_TOPIC_ERROR] {e}")
        else:
            print("⚠️ Aucun topic_id trouvé pour ce client PWA")

        # ============================================================
        # 4) Déclenchement unlock PWA (existant - inchangé)
        # ============================================================
        if channel == "pwa" and client_key and content_id and seller_slug:
            try:
                BRIDGE_API_URL = os.getenv("BRIDGE_API_URL")

                resp = requests.post(
                    f"{BRIDGE_API_URL}/pwa/unlock",
                    json={
                        "email": client_key,
                        "sellerSlug": seller_slug,
                        "contentId": content_id,
                        "sessionId": checkout_session_id,
                    },
                    timeout=5,
                )

                print(f"🚀 Unlock envoyé au bridge: {resp.status_code} {resp.text}")

            except Exception as e:
                print(f"❌ Erreur unlock bridge: {e}")


    # ============================================================
    # 5) PAIEMENT OFF-SESSION RÉUSSI
    # ============================================================
    if event["type"] == "payment_intent.succeeded":
        payment_intent = event["data"]["object"]

        metadata = (
            payment_intent["metadata"]
            if "metadata" in payment_intent
            else {}
        )

        channel = (
            metadata["channel"]
            if "channel" in metadata
            else None
        )

        if channel == "novapulse_off_session":

            try:
                client_key = (
                    metadata["client_key"]
                    if "client_key" in metadata
                    else None
                )

                seller_slug = (
                    metadata["seller_slug"]
                    if "seller_slug" in metadata
                    else None
                )

                admin_id = (
                    metadata["admin_id"]
                    if "admin_id" in metadata
                    else None
                )

                topic_id = (
                    metadata["topic_id"]
                    if "topic_id" in metadata
                    else None
                )

                amount_cents = int(
                    payment_intent["amount_received"]
                    if "amount_received" in payment_intent
                    else 0
                )

                customer_id = (
                    payment_intent["customer"]
                    if "customer" in payment_intent
                    else ""
                )

                payment_method_id = (
                    payment_intent["payment_method"]
                    if "payment_method" in payment_intent
                    else ""
                )

                payment_intent_id = (
                    payment_intent["id"]
                    if "id" in payment_intent
                    else ""
                )

                print(
                    "💳 OFF-SESSION WEBHOOK SUCCESS :",
                    payment_intent_id,
                    client_key,
                    amount_cents
                )

                airtable_url = (
                    f"https://api.airtable.com/v0/"
                    f"{BASE_ID}/{PAYMENT_LINKS_TABLE.replace(' ', '%20')}"
                )

                headers = {
                    "Authorization": f"Bearer {AIRTABLE_API_KEY}",
                    "Content-Type": "application/json"
                }

                # Vérification anti-doublon
                formula = (
                    f"{{Stripe Payment Intent ID}}="
                    f"'{payment_intent_id}'"
                )

                check_resp = requests.get(
                    airtable_url,
                    headers=headers,
                    params={
                        "filterByFormula": formula,
                        "maxRecords": 1
                    },
                    timeout=10
                )

                existing = check_resp.json().get("records", [])

                if existing:
                    print(
                        "⚠️ OFF-SESSION déjà enregistré :",
                        payment_intent_id
                    )

                else:
                    invoice_number = (
                        f"NP-{datetime.utcnow().strftime('%Y%m%d-%H%M%S')}"
                    )

                    fields = {
                        "Client Key": client_key or "",
                        "ADMIN ID": str(admin_id or ""),
                        "Amount Cents": amount_cents,
                        "Status": "Paid",
                        "Paid At": datetime.utcnow().isoformat(),
                        "Sent At": datetime.utcnow().isoformat(),
                        "Invoice Number": invoice_number,
                        "Stripe Customer ID": customer_id,
                        "Stripe Payment Intent ID": payment_intent_id,
                        "Stripe Payment Method ID": payment_method_id,
                        "Caption": "Encaissement off-session",
                        "Content ID": (
                            f"{seller_slug}_offsession_"
                            f"{payment_intent_id}"
                        ),
                    }

                    create_resp = requests.post(
                        airtable_url,
                        headers=headers,
                        json={"fields": fields},
                        timeout=10
                    )

                    print(
                        "💾 OFF-SESSION AIRTABLE :",
                        create_resp.status_code,
                        create_resp.text
                    )

                    if create_resp.status_code not in (200, 201):
                        print(
                            "❌ Erreur création Payment Links off-session"
                        )
                    else:
                        montant_euros = round(amount_cents / 100, 2)

                        try:
                            BRIDGE_API_URL = os.getenv("BRIDGE_API_URL")

                            if client_key and seller_slug and BRIDGE_API_URL:
                                notify_resp = requests.post(
                                    f"{BRIDGE_API_URL}/pwa/send-admin-message",
                                    json={
                                        "email": client_key,
                                        "sellerSlug": seller_slug,
                                        "text": (
                                            f"✅ Paiement du solde effectué\n\n"
                                            f"Le solde restant de {montant_euros:.2f} € "
                                            f"a été débité sur le moyen de paiement enregistré, "
                                            f"conformément aux modalités de paiement acceptées lors de la validation du devis."
                                        ),
                                    },
                                    timeout=5,
                                )

                                print(
                                    "📩 OFF-SESSION CONFIRMATION CLIENT :",
                                    notify_resp.status_code,
                                    notify_resp.text
                                )

                        except Exception as e:
                            print(
                                "❌ OFF-SESSION CLIENT NOTIFY ERROR :",
                                e
                            )
            except Exception as e:
                print(
                    "❌ OFF-SESSION WEBHOOK ERROR :",
                    e
                )


    return {"status": "ok"}