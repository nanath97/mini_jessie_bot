from fastapi import FastAPI, Request
from aiogram import Bot, Dispatcher, types
import os
from dotenv import load_dotenv
from bott_webhook import register_handlers

load_dotenv()

TOKEN = os.getenv('BOT_TOKEN')
bot = Bot(token=TOKEN)
dp = Dispatcher(bot=bot)

register_handlers(bot, dp)

app = FastAPI()

@app.post(f"/bot/{TOKEN}")
async def telegram_webhook(request: Request):
    try:
        data = await request.json()
        update = types.Update(**data)
        await dp.process_update(update)
    except Exception as e:
        print("Erreur dans webhook :", e)
        return {"ok": False, "error": str(e)}
    return {"ok": True}