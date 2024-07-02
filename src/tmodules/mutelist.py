import asyncio
import json
from datetime import timedelta
from pathlib import Path

from telethon import events
from telethon.tl.types import PeerChannel


def get_or_create_mutelist(mfp: Path):
    if mfp.exists():
        return json.loads(mfp.read_text())

    mutelist = {"channels": {}}
    with open(mfp, "w+") as mf:
        json.dump(mutelist, mf, indent=4)
    return mutelist


def save_mutelist(mfp: Path, mutelist: dict):
    with open(mfp, "w+") as mf:
        json.dump(mutelist, mf, indent=4)


async def init(client, logger, config, **context):
    owner = int(config.get("general", "owner"))
    target_id = config.getint("general", "target_id")
    mutelist_data_fp = Path(config.get("mutelist", "filepath"))

    mstore = get_or_create_mutelist(mutelist_data_fp)
    logger.info("Initiating mutelist (for %s, %s items) ...", target_id, len(mstore["channels"]))

    @client.on(events.NewMessage(chats=[target_id]))
    async def mutelist_handler(event):
        if not event.fwd_from:
            return

        fwd_from = event.fwd_from.from_id
        if not isinstance(fwd_from, PeerChannel):
            return

        cid = fwd_from.channel_id
        if minutes := mstore["channels"].get(str(cid)):
            delta = timedelta(minutes=int(minutes))
            await event.client.edit_permissions(event.chat, event.sender, delta, send_messages=False, send_media=False)
            return

    @client.on(events.NewMessage(pattern=r"/addmute\s(\d+)m", from_users=[owner]))
    async def mutelist_add(event):
        if not event.is_reply:
            return await event.delete()

        minutes = int(event.pattern_match.group(1))
        message = await event.get_reply_message()
        if not message.fwd_from:
            return await event.delete()

        fwd_from = message.fwd_from.from_id
        if not isinstance(fwd_from, PeerChannel):
            return await event.delete()

        cid = fwd_from.channel_id
        resp = await event.reply(f"Added channel [ID {cid}]: {minutes} minutes.")
        mstore["channels"][str(cid)] = minutes
        save_mutelist(mutelist_data_fp, mstore)
        await asyncio.sleep(3)
        return await event.delete(), await resp.delete()

    @client.on(events.NewMessage(pattern=r"/rmmute", from_users=[owner]))
    async def mutelist_rm(event):
        if not event.is_reply:
            return await event.delete()

        message = await event.get_reply_message()
        if not message.fwd_from:
            return await event.delete()

        fwd_from = message.fwd_from.from_id
        if not isinstance(fwd_from, PeerChannel):
            return await event.delete()

        cid = fwd_from.channel_id
        resp = await event.reply(f"Removed channel [ID {cid}]!")
        del mstore["channels"][str(cid)]
        save_mutelist(mutelist_data_fp, mstore)
        await asyncio.sleep(3)
        return await event.delete(), await resp.delete()
