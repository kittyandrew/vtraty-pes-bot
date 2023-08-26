from telethon import events
from pprint import pprint
import asyncio
import os, re


async def init(client, logger, config, **context):
    owner = int(config.get("general", "owner"))
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
            text = (
                "New user in the group\n\n"
                f"Fullname: <code>{u.first_name} {u.last_name or ''}</code>\n"
                f"Username: <code>{'@' + u.username if u.username else '-' * 10}</code>\n"
                f"Id: <code>{u.id}</code>\n\n"
                f"Phone: <code>{u.phone or '-' * 10}</code>"
            )
            await client.send_message(owner, text, parse_mode="html")
