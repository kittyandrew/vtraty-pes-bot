from telethon import events
from pprint import pprint
import asyncio
import os, re


async def init(client, logger, config, **context):
    owner = config.get("general", "owner")
    target_id = config.getint("general", "target_id")
    target_text = config.get("general", "target_text")

    logger.info("Initiating gatekeeper ...")

    @client.on(events.ChatAction(chats=[target_id]))
    async def gatekeeper(event):
        if event.user_joined:
            await asyncio.sleep(2)
            await event.reply(target_text)

