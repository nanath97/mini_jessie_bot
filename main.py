from fastapi import FastAPI
from bott_webhook import router as bot_router  # pour Telegram et ventes individuelles
from stripe_webhook_groupe import router as groupe_router  # pour les ventes groupées Stripe

app = FastAPI()

# On relie les routes du bot Telegram
app.include_router(bot_router)

# On relie les routes Stripe pour paiements groupés
app.include_router(groupe_router)







load_dotenv()


app = FastAPI()

@app.post(f"/bot/{os.getenv('BOT_TOKEN')}")
async def telegram_webhook(request: Request):
    try:
        data = await request.json()
        update = types.Update(**data)
        await dp.process_update(update)
    except Exception as e:
        print("Erreur dans webhook :", e)
        return {"ok": False, "error": str(e)}
    return {"ok": True}


@app.on_event("startup")
async def startup_event():
    try:
        import bott_webhook
        bott_webhook.initialize_authorized_users()
        print(f"[STARTUP] Initialisation des utilisateurs VIP terminée.")
    except Exception as e:
        print(f"[STARTUP ERROR] Erreur pendant le chargement des VIP : {e}")

# === 221097 DEBUT
app.include_router(stripe_router)
# === 221097 FIN

print("🔥 >>> FICHIER MAIN.PY BIEN LANCÉ <<< 🔥")

# === 221097 FINV1