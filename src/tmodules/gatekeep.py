from telethon import events
from pprint import pprint
import asyncio
import os, re
import pytz


async def init(client, logger, config, **context):
    owner = int(config.get("general", "owner"))
    timezone = pytz.timezone(config.get("general", "timezone"))
    target_id = config.getint("general", "target_id")
    target_text = config.get("general", "target_text")

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

            text = (
                "New user in the group\n\n"
                f"Fullname: <code>{u.first_name} {u.last_name or ''}</code>\n"
                f"Username: <code>{'@' + u.username if u.username else '-' * 10}</code>\n"
                f"Id: <code>{u.id}</code>\n\n"
                f"Phone: <code>{u.phone or '-' * 10}</code>\n"
                f"Photo: <code>{photo_date}</code>\n"
            )
            await client.send_message(owner, text, parse_mode="html")
