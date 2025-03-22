import asyncio
import tempfile
import urllib.parse
from pathlib import Path
from secrets import token_urlsafe
from typing import Optional

import aiofiles
import aiohttp
import yt_dlp
from telethon import events
from telethon.tl.types import DocumentAttributeVideo, MessageEntityUrl


def validate_url(source: str, domains: list[str]):
    if not source.startswith("http"):
        source = f"http://{source}"
    parsed = urllib.parse.urlparse(source)
    return parsed.hostname and any(parsed.hostname == domain for domain in domains)


def download_by_url(url: str, output_dir: str):
    path = Path(output_dir) / f"{token_urlsafe(16)}.mp4"
    with yt_dlp.YoutubeDL({"outtmpl": str(path), "progress_hooks": [lambda _: None]}) as ydl:
        result = ydl.extract_info(url, download=True)
    return result, path


async def download_thumb(info, output_dir: str) -> Optional[Path]:
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
    logger.info("Initiating twitter reposter ...")

    @client.on(events.NewMessage(func=lambda e: e.text and e.entities and not (e.is_channel and not e.is_group)))
    async def twitter_reposter(event):
        if event.file:
            logger.warning("Skipping potential twitter link, cuz its already has file: %s", event)
            return

        for item in event.entities:
            if not isinstance(item, MessageEntityUrl):
                continue

            url = event.raw_text[item.offset : item.offset + item.length]
            if not validate_url(url, ["x.com"]):
                continue

            logger.info("Processing url [maybe x.com video]: '%s' ...", url)
            try:
                with tempfile.TemporaryDirectory() as output_dir:
                    try:
                        info, fp = await asyncio.to_thread(download_by_url, url, output_dir)
                        assert info is not None, f"Something real broken (info={info})!"
                        assert info.get("duration") is not None, f"GIF.. do we support gifs?"
                    except (yt_dlp.utils.DownloadError, AssertionError) as e:
                        logger.warning("[%s]: Failed downloading ('%s'), just replacing url ...", url, e)
                        await event.reply(url.replace("x.com/", "fxtwitter.com/"))
                        continue

                    attributes = DocumentAttributeVideo(info["duration"], info["width"], info["height"])
                    thumb = await download_thumb(info, output_dir)
                    logger.info("Attempted to prepare thumbnail for the video: '%s' ...", thumb)

                    tg_file = await event.client.upload_file(fp)

                    # @TODO: We currently skip original description if it's a sub-tweet,
                    #  instead this should be a double quote or sub-quote somehow.
                    if description := info.get("description"):
                        if (words := description.split(" "))[-1].startswith("https://t.co/"):
                            description = " ".join(words[:-1]).replace("  ", "\n\n")
                        message = f'<blockquote>{description}</blockquote>\n\n- <a href="{url}">{info['uploader']}</a>'
                    else:
                        message = f'- <a href="{url}">{info['uploader']}</a>'

                    await event.reply(message, file=tg_file, attributes=[attributes], thumb=thumb, parse_mode="html")
                    logger.info("Uploaded video for x.com url: '%s' ...", url)
            except Exception as e:
                logger.exception(e)
