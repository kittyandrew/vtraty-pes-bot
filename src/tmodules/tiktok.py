from telethon.tl.types import MessageEntityUrl
from secrets import token_urlsafe
from telethon import events
from pprint import pprint
from pathlib import Path
import urllib.parse
import tempfile
import asyncio
import yt_dlp
import os, re


tt_reg = re.compile(r"tiktok.com")


def download_by_url(url: str, output_dir: str) -> None:
    path = Path(output_dir) / f"{token_urlsafe(16)}.mp4"
    ydl_opts = {
        "outtmpl": str(path),
        "progress_hooks": [lambda x: None],
    }

    # Download video with youtube-dl, passing options
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        result = ydl.extract_info(url, download=True)
        # pprint(result)
        # ydl.download([url])

    return path, result["creator"], result["display_id"]


async def init(client, logger, config, **context):
    owner = config.get("general", "owner")
    # target_id = config.getint("general", "target_id")

    logger.info("Initiating tiktok reposter ...")

    @client.on(events.NewMessage(func=lambda e: e.text and e.entities))
    async def tiktok_reposter(event):
        for item in event.entities:
            if not isinstance(item, MessageEntityUrl): continue

            url = event.raw_text[item.offset:item.offset+item.length]
            # Some lame basic check.
            if "tiktok.com" not in url: continue

            logger.info("Processing url [maybe tiktok video]: '%s' ...", url)
            try:
                with tempfile.TemporaryDirectory() as output_dir:
                    # @TODO: This is blocking.
                    fp, user, video_id = download_by_url(url, output_dir)
                    tg_file = await event.client.upload_file(fp)

                tt_url = f"https://www.tiktok.com/@{urllib.parse.quote(user, safe='')}/video/{video_id}"
                message = f"<a href='{tt_url}'>{tt_url}</a>"
                await event.reply(message, file=tg_file, parse_mode="html")
                logger.info("Uploaded video for tiktok url: '%s' ...", tt_url)
            except Exception as e:
                logger.error(e)

