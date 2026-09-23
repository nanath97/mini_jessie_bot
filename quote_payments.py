"""Quote payment rules. Dependencies are injected; no live services at import."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from threading import RLock
from urllib.parse import quote


# The checked-in supervisor runs one Python worker. This is not a distributed lock.
payment_lock = RLock()


class PaymentRuleError(ValueError):
    pass


def stripe_response_dict(value):
    """Normalize SDK responses explicitly; StripeObject does not support dict.get."""
    result = value if isinstance(value, dict) else value.to_dict()
    if not isinstance(result, dict):
        raise TypeError("Stripe to_dict() did not return a dict")
    return result


def formula_value(value):
    return str(value).replace("\\", "\\\\").replace("'", "\\'")


def euros_equal(value, cents):
    try:
        return Decimal(str(value).replace(",", ".")) * 100 == cents
    except InvalidOperation:
        return False


def utc_datetime(value):
    try:
        result = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return result.replace(tzinfo=timezone.utc) if result.tzinfo is None else result.astimezone(timezone.utc)
    except (TypeError, ValueError):
        raise PaymentRuleError("Sent At absent ou invalide : encaissement du solde refusé.")


def require_due(fields, now=None):
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    due = utc_datetime(fields.get("Sent At")) + timedelta(hours=24)
    if now < due:
        minutes = int((due - now).total_seconds() + 59) // 60
        raise PaymentRuleError(f"Le délai de 24 h n'est pas encore écoulé. Encore {minutes} minute(s).")


class QuotePayments:
    def __init__(self, http, base_id, api_key):
        self.http = http
        self.root = f"https://api.airtable.com/v0/{base_id}"
        self.headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    def url(self, table, record_id=None):
        result = f"{self.root}/{quote(table, safe='')}"
        return result if record_id is None else f"{result}/{quote(record_id, safe='')}"

    def records(self, table, formula):
        params = {"filterByFormula": formula}
        records = []
        seen = set()
        while True:
            response = self.http.get(self.url(table), headers=self.headers, params=dict(params), timeout=10)
            response.raise_for_status()
            data = response.json()
            if not isinstance(data.get("records"), list):
                raise PaymentRuleError("Lecture Airtable incomplète : paiement refusé.")
            records.extend(data["records"])
            offset = data.get("offset")
            if not offset:
                return records
            if offset in seen:
                raise PaymentRuleError("Pagination Airtable incohérente.")
            seen.add(offset)
            params["offset"] = offset

    def get(self, record_id):
        if not record_id:
            raise PaymentRuleError("Référence Payment Links manquante.")
        response = self.http.get(self.url("Payment Links", record_id), headers=self.headers, timeout=10)
        response.raise_for_status()
        record = response.json()
        if record.get("id") != record_id or not isinstance(record.get("fields"), dict):
            raise PaymentRuleError("Référence Payment Links incohérente.")
        return record

    def patch(self, record_id, fields):
        response = self.http.patch(self.url("Payment Links", record_id), headers=self.headers,
                                   json={"fields": fields}, timeout=10)
        response.raise_for_status()
        return response

    def quote_payments(self, quote_id):
        return self.records("Payment Links", f"{{Quote ID}}='{formula_value(quote_id)}'")

    def find_balance_quote(self, email, seller_slug, amount_cents):
        records = self.records("Quotes", f"AND({{client_email}}='{formula_value(email)}',"
                               f"{{seller_slug}}='{formula_value(seller_slug)}',{{status}}='accepted')")
        matches = []
        for record in records:
            fields = record.get("fields", {})
            qid = fields.get("quote_id")
            if not qid or not self.coherent_quote(fields, email, seller_slug, amount_cents):
                continue
            payment_records = self.quote_payments(qid)
            payments = [r.get("fields", {}) for r in payment_records]
            if not any(p.get("Quote ID") == qid and p.get("Payment Role") == "deposit"
                       and p.get("Status") == "Paid" for p in payments):
                continue
            balances = self.balance_records(payment_records, qid)
            if balances:
                incomplete = [r for r in balances if r["fields"].get("Status") == "Pending"
                              and not r["fields"].get("Sent At")]
                if not incomplete:
                    continue
                if len(balances) != 1:
                    raise PaymentRuleError("Plusieurs soldes pour ce devis : reprise automatique refusée.")
                self.require_incomplete(balances[0], qid, email, amount_cents)
            matches.append({"quote_id": qid, "remaining_amount": fields.get("remaining_amount")})
        if len(matches) > 1:
            raise PaymentRuleError("Plusieurs devis possibles pour ce montant : association automatique du solde refusée.")
        return matches[0] if matches else None

    @staticmethod
    def balance_records(records, quote_id):
        return [r for r in records if r.get("fields", {}).get("Quote ID") == quote_id
                and r["fields"].get("Payment Role") == "balance"
                and r["fields"].get("Status") in ("Pending", "Paid")]

    @staticmethod
    def require_incomplete(record, quote_id, email, amount_cents):
        fields = record.get("fields", {})
        if (not record.get("id") or fields.get("Quote ID") != quote_id
                or fields.get("Client Key") != email or fields.get("Amount Cents") != amount_cents
                or fields.get("Payment Role") != "balance" or fields.get("Status") != "Pending"
                or fields.get("Sent At") or fields.get("Stripe Payment Intent ID")
                or not fields.get("Content ID") or not fields.get("Checkout Session ID")):
            raise PaymentRuleError("Solde déjà envoyé, payé, engagé ou incohérent : reprise refusée.")
        return record

    @staticmethod
    def coherent_quote(fields, email, seller_slug, amount_cents):
        return (fields.get("client_email") == email and fields.get("seller_slug") == seller_slug
                and fields.get("status") == "accepted"
                and euros_equal(fields.get("remaining_amount"), amount_cents))

    def validate_balance(self, record, email, seller_slug, amount_cents, quote_id=None, now=None):
        fields = record.get("fields", {})
        qid = fields.get("Quote ID")
        if (not record.get("id") or not qid or (quote_id and qid != quote_id)
                or fields.get("Client Key") != email or fields.get("Payment Role") != "balance"
                or fields.get("Status") != "Pending" or fields.get("Amount Cents") != amount_cents
                or not fields.get("Checkout Session ID") or not fields.get("Content ID")):
            raise PaymentRuleError("Solde modifié, déjà payé ou incohérent : prélèvement refusé.")
        require_due(fields, now)
        if fields.get("Stripe Payment Intent ID"):
            raise PaymentRuleError("Un prélèvement est déjà engagé pour ce solde. Vérification nécessaire.")
        quotes = self.records("Quotes", f"{{quote_id}}='{formula_value(qid)}'")
        if (len(quotes) != 1 or quotes[0].get("fields", {}).get("quote_id") != qid
                or not self.coherent_quote(quotes[0]["fields"], email, seller_slug, amount_cents)):
            raise PaymentRuleError("Devis du solde incohérent avec le client, le vendeur ou le montant.")
        payments = [r.get("fields", {}) for r in self.quote_payments(qid)]
        if not any(p.get("Quote ID") == qid and p.get("Payment Role") == "deposit"
                   and p.get("Status") == "Paid" for p in payments):
            raise PaymentRuleError("Aucun acompte Paid pour ce devis : prélèvement refusé.")
        return record

    def find_pending_balance(self, email, seller_slug, amount_cents, now=None):
        records = self.records("Payment Links", f"AND({{Client Key}}='{formula_value(email)}',"
                               "{Payment Role}='balance',{Status}='Pending')")
        candidates = []
        for record in records:
            fields = record.get("fields", {})
            qid = fields.get("Quote ID")
            if (not qid or fields.get("Client Key") != email
                    or fields.get("Payment Role") != "balance" or fields.get("Status") != "Pending"):
                continue
            quotes = self.records("Quotes", f"{{quote_id}}='{formula_value(qid)}'")
            owned = [q for q in quotes if q.get("fields", {}).get("client_email") == email
                     and q["fields"].get("seller_slug") == seller_slug]
            if not owned:
                continue
            if len(quotes) != 1 or owned[0]["fields"].get("quote_id") != qid:
                raise PaymentRuleError("Devis ambigu : encaissement refusé.")
            if owned[0]["fields"].get("status") == "accepted":
                candidates.append(record)
        if len(candidates) > 1:
            raise PaymentRuleError("Plusieurs soldes Pending pour ce client et ce vendeur : encaissement refusé.")
        if not candidates:
            raise PaymentRuleError("Aucun solde de devis accepté n’est actuellement éligible à l’encaissement pour ce client.")
        record = candidates[0]
        balance_cents = record["fields"].get("Amount Cents")
        if not isinstance(balance_cents, int) or isinstance(balance_cents, bool) or balance_cents <= 0:
            raise PaymentRuleError("Montant du solde incohérent : encaissement refusé.")
        # Validate the actual debt before disclosing its amount or accepting a command.
        self.validate_balance(record, email, seller_slug, balance_cents, now=now)
        if amount_cents != balance_cents:
            amount = f"{balance_cents / 100:.2f}".replace(".", ",")
            raise PaymentRuleError(f"Le solde restant dû pour ce devis est de {amount} €.\n"
                                   "La commande doit correspondre exactement au solde du devis.")
        return record


def resolve_env_payment(deposit_lookup, balance_lookup, email, seller_slug, amount_cents):
    deposit = deposit_lookup(email=email, seller_slug=seller_slug, amount_cents=amount_cents)
    if deposit:
        return deposit["quote_id"], "deposit"
    balance = balance_lookup(email=email, seller_slug=seller_slug, amount_cents=amount_cents)
    return (balance["quote_id"], "balance") if balance else ("", "")


def prepare_balance_link(store, stripe_api, create_checkout, save_payment, *, quote_id,
                         email, seller_slug, amount_cents, content_id, admin_id, buyer_type, caption):
    """Resume the same unpaid row, including when a Bridge response was lost."""
    with payment_lock:
        match = store.find_balance_quote(email, seller_slug, amount_cents)
        if not match or match["quote_id"] != quote_id:
            raise PaymentRuleError("Le solde n'est plus éligible à cet envoi.")
        balances = store.balance_records(store.quote_payments(quote_id), quote_id)
        if len(balances) > 1:
            raise PaymentRuleError("Plusieurs soldes pour ce devis : reprise automatique refusée.")
        record = None
        if balances:
            record = store.require_incomplete(store.get(balances[0]["id"]), quote_id, email, amount_cents)
            fields = record["fields"]
            content_id = fields["Content ID"]
            session = stripe_response_dict(stripe_api.checkout.Session.retrieve(fields["Checkout Session ID"]))
            metadata = stripe_response_dict(session.get("metadata") or {})
            if (session.get("amount_total") != amount_cents or session.get("payment_status") != "unpaid"
                    or metadata.get("client_key") != email or metadata.get("seller_slug") != seller_slug
                    or metadata.get("content_id") != content_id):
                raise PaymentRuleError("Checkout déjà payé ou incohérent : reprise refusée.")
            if session.get("status") == "open":
                checkout_url = session.get("url") or fields.get("Payment Link URL")
                if not checkout_url:
                    raise PaymentRuleError("URL Checkout absente : reprise refusée.")
                return checkout_url, fields["Checkout Session ID"], content_id, record["id"]
            if session.get("status") != "expired":
                raise PaymentRuleError("État Checkout indéterminé : reprise refusée.")
            # Only a confirmed expired, unpaid session can be replaced safely.
        checkout_url, session_id = create_checkout(
            amount_cents=amount_cents, client_key=email, content_id=content_id,
            seller_slug=seller_slug, admin_id=admin_id, buyer_type=buyer_type,
        )
        if record:
            store.patch(record["id"], {"Payment Link URL": checkout_url, "Checkout Session ID": session_id})
            record_id = record["id"]
        else:
            response = save_payment(
                client_key=email, content_id=content_id, payment_link=checkout_url,
                admin_id=admin_id, amount_cents=amount_cents, checkout_session_id=session_id,
                caption=caption, quote_id=quote_id, payment_role="balance",
            )
            response.raise_for_status()
            record_id = response.json()["id"]
        return checkout_url, session_id, content_id, record_id


def persist_checkout_balance(store, record_id, session_id, buyer_fields, seller_slug,
                             next_invoice, enqueue, context=None):
    """Fresh read through enqueue is serialized with off-session balance persistence."""
    with payment_lock:
        record = store.get(record_id)
        fields = record["fields"]
        incoming_pi = (buyer_fields or {}).get("Stripe Payment Intent ID")
        if (fields.get("Payment Role") != "balance" or not fields.get("Quote ID")
                or fields.get("Checkout Session ID") != session_id or not incoming_pi):
            raise PaymentRuleError("Checkout balance : identité incohérente.")
        if fields.get("Status") == "Paid":
            if fields.get("Stripe Payment Intent ID") == incoming_pi:
                return record_id
            raise PaymentRuleError("Balance déjà Paid avec un autre PaymentIntent.")
        if (fields.get("Status") != "Pending"
                or fields.get("Stripe Payment Intent ID") not in (None, "", incoming_pi)):
            raise PaymentRuleError("Checkout balance : statut ou PaymentIntent incohérent.")
        updates = dict(buyer_fields or {})
        updates.update({"Status": "Paid", "Paid At": datetime.now(timezone.utc).isoformat(),
                        "Invoice Number": next_invoice(seller_slug)})
        response = store.patch(record_id, updates)
        enqueue(response, seller_slug, context or {})
        return record_id


def close_balance_checkout(stripe_api, record, email, seller_slug, amount_cents):
    """Do not charge a balance whose Checkout has already completed at Stripe."""
    fields = record["fields"]
    session = stripe_response_dict(stripe_api.checkout.Session.retrieve(fields["Checkout Session ID"]))
    metadata = stripe_response_dict(session.get("metadata") or {})
    if (session.get("amount_total") != amount_cents or metadata.get("client_key") != email
            or metadata.get("seller_slug") != seller_slug
            or metadata.get("content_id") != fields["Content ID"]):
        raise PaymentRuleError("Session Checkout incohérente avec le solde.")
    if session.get("payment_status") != "unpaid" or session.get("status") == "complete":
        raise PaymentRuleError("Checkout déjà payé ou terminé : prélèvement du solde refusé.")
    if session.get("status") == "open":
        session = stripe_response_dict(stripe_api.checkout.Session.expire(fields["Checkout Session ID"]))
    if session.get("status") != "expired":
        raise PaymentRuleError("Impossible de fermer le Checkout avant le prélèvement.")


def persist_balance_payment(store, intent, next_invoice, enqueue, context=None):
    """Patch the designated row once. Never create a replacement balance row."""
    intent = stripe_response_dict(intent)
    metadata = stripe_response_dict(intent.get("metadata") or {})
    record_id = metadata.get("payment_link_record_id")
    with payment_lock:
        record = store.get(record_id)
        fields = record["fields"]
        if (not intent.get("id") or not metadata.get("quote_id") or not metadata.get("seller_slug")
                or metadata.get("payment_role") != "balance"
                or fields.get("Client Key") != metadata.get("client_key")
                or fields.get("Quote ID") != metadata.get("quote_id")
                or fields.get("Payment Role") != "balance"
                or fields.get("Amount Cents") != intent.get("amount_received")):
            raise PaymentRuleError("Webhook solde : identité ou montant incohérent.")
        if fields.get("Status") == "Paid":
            if fields.get("Stripe Payment Intent ID") == intent["id"]:
                return None
            raise PaymentRuleError("Webhook solde : déjà Paid avec un autre PaymentIntent.")
        if fields.get("Status") != "Pending":
            raise PaymentRuleError("Webhook solde : statut différent de Pending.")
        if fields.get("Stripe Payment Intent ID") not in (None, "", intent["id"]):
            raise PaymentRuleError("Webhook solde : un autre PaymentIntent est déjà associé.")
        response = store.patch(record_id, {
            "Status": "Paid", "Paid At": datetime.now(timezone.utc).isoformat(),
            "Invoice Number": next_invoice(metadata["seller_slug"]),
            "Stripe Customer ID": intent.get("customer") or "",
            "Stripe Payment Intent ID": intent["id"],
            "Stripe Payment Method ID": intent.get("payment_method") or "",
        })
        enqueue(response, metadata["seller_slug"], context or {})
        return response


def off_session_message(amount_cents, payment_role):
    amount = f"{amount_cents / 100:.2f}"
    if payment_role == "balance":
        return f"✅ Paiement du solde effectué ! Le solde de {amount} € a été débité sur le moyen de paiement enregistré."
    return f"✅ Paiement de {amount} € effectué sur le moyen de paiement enregistré."
