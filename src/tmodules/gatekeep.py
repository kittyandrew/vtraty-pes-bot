from datetime import datetime
from telethon import events
from pprint import pprint
from time import time
import numpy as np
import asyncio
import os, re
import pytz
import json


def load_data(fp: str):
    ids, dates = [], []
    with open(fp) as f:
        data = json.load(f)
        for item in data:
            ids.append(item["id"])
            dates.append(item["time"])
    return np.array(ids), np.array(dates)


async def init(client, logger, config, **context):
    owner = int(config.get("general", "owner"))
    timezone = pytz.timezone(config.get("general", "timezone"))
    target_id = config.getint("general", "target_id")
    target_text = config.get("general", "target_text")
    historical_data_fp = config.get("guesstimator", "historical")

    logger.info("Initiating gatekeeper ...")

    @client.on(events.ChatAction(chats=[target_id]))
    async def gatekeeper(event):
        if event.user_joined:
            await asyncio.sleep(2)
            await event.reply(target_text)

            assert event.user
            u = event.user

            # Profile photo processing bit (displaying when current pfp was set).
            photo_date = "-" * 10
            async for photo in client.iter_profile_photos(u, limit=50):
                if u.photo.photo_id == photo.id:
                    photo_date = photo.date.astimezone(timezone).strftime("%Y-%m-%d %H:%M")

            guess_dt = "unknown"
            # Doing guesstimate for user creation date.
            if os.path.exists(historical_data_fp):
                x_data, y_data = load_data(historical_data_fp)
                fitted = np.polyfit(x_data, y_data, 3)
                interp = np.poly1d(fitted)

                guess, current = interp(u.id), time()
                if guess > current: guess = current
                guess_dt = datetime.utcfromtimestamp(guess).astimezone(timezone).strftime("%m/%Y")

            text = (
                "New user in the group\n\n"
                f"Fullname: <code>{u.first_name} {u.last_name or ''}</code>\n"
                f"Username: <code>{'@' + u.username if u.username else '-' * 10}</code>\n"
                f"Id: <code>{u.id}</code> (~{guess_dt})\n\n"
                f"Phone: <code>{u.phone or '-' * 10}</code>\n"
                f"Photo: <code>{photo_date}</code>\n"
            )
            await client.send_message(owner, text, parse_mode="html")
