
import stripe
import os
from decimal import Decimal



# payment_links.py

liens_paiement = {
    "1": "https://buy.stripe.com/00g5ooedBfoK07u6oE",
    "3": "https://buy.stripe.com/9B68wOdtb93hfUV1rf7AI0j",
    "9": "https://buy.stripe.com/7sYfZg2OxenB389gm97AI0G",
    "14": "https://buy.stripe.com/aEUeYYd9xfoKaM8bIL",
    "19": "https://buy.stripe.com/5kAaIId9x90mbQc148",
    "24": "https://buy.stripe.com/7sI2cc0mL90m2fC3ch",
    "29": "https://buy.stripe.com/9AQcQQ5H5gsOdYkeV0",
    "34": "https://buy.stripe.com/6oE044d9x90m5rOcMT",
    "39": "https://buy.stripe.com/dRmbJ088Rcft8st0nb7AI2d",
    "49": "https://buy.stripe.com/9AQ6ss0mL7Wi2fCdR0",
    "59": "https://buy.stripe.com/3csdUUfhFdgC6vS7sD",
    "69": "https://buy.stripe.com/cN21880mLb8udYk00c",
    "79": "https://buy.stripe.com/6oE8AA1qPccyf2o28l",
    "89": "https://buy.stripe.com/5kAeYYglJekG2fC7sG",
    "99": "https://buy.stripe.com/bJe7sK3SBfrF2457PD7AI2c"
}


stripe.api_key = os.getenv("STRIPE_SECRET_KEY")

def create_dynamic_checkout(amount_str, bot_username):
    # Normalisation
    amount_str = amount_str.replace(",", ".")
    amount_decimal = Decimal(amount_str)
    amount_cents = int(amount_decimal * 100)

    session = stripe.checkout.Session.create(
        payment_method_types=["card"],
        line_items=[{
            "price_data": {
                "currency": "eur",
                "product_data": {
                    "name": "Paiement NovaPulse"
                },
                "unit_amount": amount_cents,
            },
            "quantity": 1,
        }],
        mode="payment",
        success_url=f"https://t.me/{bot_username}?start=cdan{amount_cents}",
        cancel_url=f"https://t.me/{bot_username}",
    )

    return session.url
