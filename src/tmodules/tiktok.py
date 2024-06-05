import asyncio
import os
import re
import tempfile
import urllib.parse
from pathlib import Path
from pprint import pprint
from secrets import token_urlsafe

import aiofiles
import aiohttp
import yt_dlp
from telethon import events
from telethon.tl.types import DocumentAttributeVideo, MessageEntityUrl

tt_reg = re.compile(r"tiktok.com")


def download_by_url(url: str, output_dir: str):
    path = Path(output_dir) / f"{token_urlsafe(16)}.mp4"
    ydl_opts = {
        "outtmpl": str(path),
        "progress_hooks": [lambda x: None],
    }

    # Download video with youtube-dl, passing options
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        result = ydl.extract_info(url, download=True)
        # pprint(result)

    return result, path, result["uploader"], result["display_id"]


async def download_thumb(info, output_dir: str) -> str:
    path = Path(output_dir) / "video_thumbnail.jpeg"

    # @TODO: We can just convert any thumbnail to jpeg.
    for thumbnail in info["thumbnails"]:
        thumb_url = thumbnail.get("url", "")
        if ".jpeg" in thumb_url:
            async with aiohttp.ClientSession() as session:
                async with session.get(thumb_url) as resp, aiofiles.open(path, "wb") as f:
                    await f.write(await resp.read())
                    return path


async def init(client, logger, config, **context):
    # target_id = config.getint("general", "target_id")

    logger.info("Initiating tiktok reposter ...")

    @client.on(events.NewMessage(func=lambda e: e.text and e.entities and not (e.is_channel and not e.is_group)))
    async def tiktok_reposter(event):
        for item in event.entities:
            if not isinstance(item, MessageEntityUrl):
                continue

            url = event.raw_text[item.offset : item.offset + item.length]
            # Some lame basic check.
            if "tiktok.com" not in url:
                continue

            logger.info("Processing url [maybe tiktok video]: '%s' ...", url)
            try:
                with tempfile.TemporaryDirectory() as output_dir:
                    # @TODO: This is blocking.
                    info, fp, user, video_id = download_by_url(url, output_dir)
                    if info["resolution"] == "audio only":
                        await event.reply("Tiktok presentation detected - can't process!", parse_mode="html")
                        logger.info("Tiktok presentation detected, can't process! (url: '%s') ...", url)
                        return

                    attributes = DocumentAttributeVideo(info["duration"], info["width"], info["height"])
                    thumb = await download_thumb(info, output_dir)
                    logger.info("Attempted to prepare thumbnail for the video: '%s' ...", thumb)

                    tg_file = await event.client.upload_file(fp)

                    tt_url = f"https://www.tiktok.com/@{urllib.parse.quote(user, safe='')}/video/{video_id}"
                    tt_display_url = f"https://www.tiktok.com/@{user}/video/{video_id}"
                    message = f"<a href='{tt_url}'>{tt_display_url}</a>"
                    await event.reply(message, file=tg_file, attributes=[attributes], thumb=thumb, parse_mode="html")
                    logger.info("Uploaded video for tiktok url: '%s' ...", tt_display_url)
            except Exception as e:
                logger.error(e)
