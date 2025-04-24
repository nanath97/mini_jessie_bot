from fastapi import FastAPI, Request
from aiogram import Bot, Dispatcher, types
import os
from dotenv import load_dotenv
from core import bot,dp
from bott_webhook import register_handlers
register_handlers(bot,dp)
load_dotenv()

register_handlers(bot, dp)

app = FastAPI()

@app.post(f"/bot/{os.getenv("BOT_TOKEN")}")
async def telegram_webhook(request: Request):
    try:
        data = await request.json()
        update = types.Update(**data)
        await dp.process_update(update)
    except Exception as e:
        print("Erreur dans webhook :", e)
        return {"ok": False, "error": str(e)}
    return {"ok": True}