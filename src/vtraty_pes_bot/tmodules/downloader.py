import asyncio
import html
import tempfile
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path
from secrets import token_urlsafe
from typing import Optional

import aiofiles
import aiohttp
import sentry_sdk
import yt_dlp
from telethon import events
from telethon.tl.types import DocumentAttributeVideo, MessageEntityUrl

MATCH_RULES = {
    "instagram": {"domains": ["instagram.com", "facebook.com"], "path": lambda p: "/reel/" in str(p)},
    "facebook": {"domains": ["facebook.com"], "path": lambda p: "/share/v/" in str(p)},
    "youtube": {"domains": ["youtube.com"], "path": lambda p: str(p).startswith("/shorts/")},
    "twitter": {"domains": ["x.com"], "path": lambda p: len(str(p).strip("/").split("/")) > 1},
    "tiktok": {"domains": ["tiktok.com", "vm.tiktok.com"], "path": lambda p: bool(p)},
}


def validate_url(source: str, rules=MATCH_RULES):
    parsed = urllib.parse.urlparse(source if source.startswith("http") else f"http://{source}")
    assert parsed.hostname, f"Somehow url without .hostname: '{source}'"

    for rname, config in rules.items():
        if parsed.hostname.removeprefix("www.") in config["domains"]:
            if config["path"](parsed.path):
                return rname
    return False


def download_by_url(url: str, output_dir: str):
    yt_dlp_config = {
        "outtmpl": str(path := Path(output_dir) / f"{token_urlsafe(16)}.mp4"),
        "progress_hooks": [lambda _: None],
        "format_sort": ["res", "vcodec:avc", "acodec:aac"],
    }
    with yt_dlp.YoutubeDL(yt_dlp_config) as ydl:
        return path, ydl.extract_info(url, download=True)


async def download_thumb(info, output_dir: str, logger) -> Optional[Path]:
    path = Path(output_dir) / "video_thumbnail.jpeg"

    # @TODO: We can just convert any thumbnail to jpeg.
    for thumbnail in info.get("thumbnails", []):
        thumb_url = thumbnail.get("url", "")
        if any(thumb_url.split("?")[0].endswith(ext) for ext in (".jpeg", ".jpg")):
            async with aiohttp.ClientSession() as session:
                async with session.get(thumb_url) as resp, aiofiles.open(path, "wb") as f:
                    await f.write(await resp.read())
                    logger.info("Attempted to prepare thumbnail for the video: '%s' ...", path)
                    return path


async def init(client, logger, config, **context):
    logger.info("Initiating shortform video downloader ...")

    @client.on(events.NewMessage(func=lambda e: e.text and e.entities and not (e.is_channel and not e.is_group)))
    async def shortform_video_downloader(event):
        # if event.file:
        #     logger.warning("Skipping potential instagram link, cuz its already has file: %s", event)
        #     return

        for item in event.entities:
            if not isinstance(item, MessageEntityUrl):
                continue

            if not (rule := validate_url(url := event.raw_text[item.offset : item.offset + item.length])):
                continue

            logger.info("Processing url [detected shortform video]: '%s' ...", url)
            sentry_sdk.add_breadcrumb(category="downloader", message=f"Downloading {rule} video", data={"url": url})
            with tempfile.TemporaryDirectory() as out_dir:
                try:
                    fp, info = await asyncio.to_thread(download_by_url, url, out_dir)
                    assert info is not None, f"Something real broken (info={info})!"
                    assert info.get("duration") is not None, f"GIF or livestream... maybe support GIFs?"
                    assert str(info.get("resolution")) != "audio only", "Audio-only (e.g. tiktok presentation), can't process!"

                    user, video_id = info["uploader"], info["display_id"]
                    upload_date = datetime.fromtimestamp(info["timestamp"], tz=timezone.utc).strftime("%d %b %Y")
                    safe_user = html.escape(user)
                    safe_url = html.escape(url, quote=True)

                    if rule == "tiktok":
                        tt_url = f"https://www.tiktok.com/@{urllib.parse.quote(user, safe='')}/video/{video_id}"
                        message = f'<a href="{tt_url}">https://www.tiktok.com/@{safe_user}/video/{video_id}</a> ({upload_date})'
                    elif description := info.get("description"):
                        # @TODO: We currently skip original description if it's a sub-tweet,
                        #  instead this should be a double quote or sub-quote somehow.
                        if rule == "twitter":
                            if (words := description.split(" "))[-1].startswith("https://t.co/"):
                                description = " ".join(words[:-1]).replace("  ", "\n\n")
                        message = f'<blockquote>{html.escape(description)}</blockquote>\n\n- <a href="{safe_url}">{safe_user}</a> ({upload_date})'
                    elif title := info.get("title"):
                        message = f'<blockquote>{html.escape(title)}</blockquote>\n\n- <a href="{safe_url}">{safe_user}</a> ({upload_date})'
                    else:
                        message = f'- <a href="{safe_url}">{safe_user}</a> ({upload_date})'

                    thumb, tg_file = await asyncio.gather(download_thumb(info, out_dir, logger), event.client.upload_file(fp))

                    attributes = DocumentAttributeVideo(info["duration"], info["width"], info["height"], supports_streaming=True)
                    await event.reply(message, file=tg_file, attributes=[attributes], thumb=thumb, parse_mode="html")
                    logger.info("Uploaded video for shortform video url: '%s' ...", url)
                except (yt_dlp.utils.DownloadError, AssertionError) as e:
                    if rule == "twitter":
                        logger.warning("[%s]: Failed downloading ('%s'), just replacing url ...", url, e)
                        await event.reply(url.replace("x.com/", "fxtwitter.com/"))
                    elif rule == "tiktok":
                        await event.reply("Failed to download, unprocessable tiktok link..", parse_mode="html")
                    else:
                        logger.error("[%s]: Failed downloading ('%s'), ignoring ...", url, e)
                except Exception:
                    logger.exception("Unexpected error processing video url: '%s'", url)
