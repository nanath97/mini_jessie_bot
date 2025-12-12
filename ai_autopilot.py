import json
import datetime
from ai_state_store import get_state, upsert_state
from aiogram import types
from config import STAFF_GROUP_ID

COOLDOWN_SECONDS = 8


async def maybe_run_autopilot(message: types.Message, topic_id: int, bot):
    # 1) TEXT ONLY
    if message.content_type != types.ContentType.TEXT:
        return

    user_id = message.from_user.id
    now = datetime.datetime.utcnow()

    state = get_state(user_id)

    # 2) Create state if not exists
    if not state:
        upsert_state(user_id, {
            "Topic ID": str(topic_id),
            "Script ID": "script_fr_v1",
            "Step Index": 0,
            "Profile JSON": "{}",
            "Heat": 0,
            "Pending Fillers JSON": "[]",
            "Autopilot": "OFF",
            "Cooldown Until": None
        })
        return

    fields = state["fields"]

    # 3) Autopilot OFF → silence
    if fields.get("Autopilot") != "ON":
        return

    # 4) Cooldown
    cooldown = fields.get("Cooldown Until")
    if cooldown:
        cd_time = datetime.datetime.fromisoformat(cooldown.replace("Z", ""))
        if now < cd_time:
            return

    # 5) MESSAGE AUTO (MVP)
    reply = "😌 Je t’ai lu… je te réponds."

    # 6) Send to client
    await bot.send_message(user_id, reply)

    # 7) Log in staff topic
    await bot.send_message(
        chat_id=STAFF_GROUP_ID,
        message_thread_id=topic_id,
        text=f"[AUTO] → {reply}"
    )

    # 8) Update cooldown
    upsert_state(user_id, {
        "Cooldown Until": (now + datetime.timedelta(seconds=COOLDOWN_SECONDS)).isoformat()
    })
