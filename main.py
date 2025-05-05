from fastapi import FastAPI, Request
from aiogram import Bot, Dispatcher, types
import os
from dotenv import load_dotenv
from core import bot, dp
import bott_webhook
from aiogram.types import BotCommand



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


# TEST AIDE A ECRITURE et le from aiogram types import botcommand aussi dans les imports
@app.on_event("startup")
async def on_startup():
    commands = [
        BotCommand(command="/dev", description="Stocker un contenu pour l’envoyer plus tard"),
        BotCommand(command="/envoyer9", description="Envoyer un contenu flouté à 9 €"),
        BotCommand(command="/envoyer14", description="Envoyer un contenu flouté à 14 €"),
        BotCommand(command="/envoyer19", description="Envoyer un contenu flouté à 19 €"),
        BotCommand(command="/envoyer24", description="Envoyer un contenu flouté à 24 €"),
        BotCommand(command="/envoyer29", description="Envoyer un contenu flouté à 29 €"),
        BotCommand(command="/envoyer34", description="Envoyer un contenu flouté à 34 €"),
        BotCommand(command="/envoyer39", description="Envoyer un contenu flouté à 39 €"),
        BotCommand(command="/envoyer44", description="Envoyer un contenu flouté à 44 €"),
        BotCommand(command="/envoyer49", description="Envoyer un contenu flouté à 49 €"),
        BotCommand(command="/envoyer59", description="Envoyer un contenu flouté à 59 €"),
        BotCommand(command="/envoyer69", description="Envoyer un contenu flouté à 69 €"),
        BotCommand(command="/envoyer79", description="Envoyer un contenu flouté à 79 €"),
        BotCommand(command="/envoyer89", description="Envoyer un contenu flouté à 89 €"),
        BotCommand(command="/envoyer99", description="Envoyer un contenu flouté à 99 €"),
    ]
    await bot.set_my_commands(commands)
