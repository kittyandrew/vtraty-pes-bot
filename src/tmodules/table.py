import asyncio
import json
from collections import defaultdict
from datetime import datetime, timedelta
from itertools import chain, zip_longest
from pathlib import Path
from secrets import token_hex

import imgkit
import jinja2
import pytz
from aiocache import Cache, cached
from telethon import Button, TelegramClient, events
from telethon.errors import MessageNotModifiedError
from telethon.tl.types import ChannelParticipantsAdmins, InputMessagesFilterPinned

from ..gsheets import get_gsheet_prompt, get_vehicle_types
from ..llm import Item, parse_messages


def get_time_range(tz):
    now = datetime.now(tz)
    # Check if we passed 6 am of the current day already.
    if (now.hour * 60 + now.minute) > (6 * 60):
        # If so, range of interest concludes today.
        end = now.replace(hour=6, minute=0)
        return end - timedelta(days=1), end
    else:
        end = now.replace(hour=6, minute=0) - timedelta(days=1)
        return end - timedelta(days=1), end


def get_cache(cache_fp: Path, date: str) -> list[Item]:
    if cache_fp.exists():
        values = json.loads(cache_fp.read_text()).get(date, [])
        return [Item.model_validate(r) for r in values]
    return []


def store_cache(cache_fp: Path, date: str, values: list[Item]):
    cache = {}
    if cache_fp.exists():
        cache = json.loads(cache_fp.read_text())

    cache[date] = [r.model_dump() for r in values]
    with open(cache_fp, "w+") as f:
        json.dump(cache, f)


def convert_counter_into_lines(counter: dict, vehicle_types):
    items = list(sorted(counter.values(), key=lambda o: o["name"], reverse=True))

    for item in items:
        for vtype in vehicle_types:
            if vtype.name == "UNKNOWN":
                item["type"] = vehicle_types.UNKNOWN
                break

            if vtype.name in item["name"]:
                item["type"] = vtype
                break

    items = list(sorted(items, key=lambda o: o["type"]))

    lines, total, damaged, destroyed, captured, olds = [], 0, 0, 0, 0, 0
    for value in items:
        statuses, old = [], ""
        total += value["count"]
        if value["destroyed"]:
            statuses.append(f"{value['destroyed']}x DESTROYED")
            destroyed += value["destroyed"]
        if value["damaged"]:
            statuses.append(f"{value['damaged']}x DAMAGED")
            damaged += value["damaged"]
        if value["captured"]:
            statuses.append(f"{value['captured']}x CAPTURED")
            captured += value["captured"]
        if value["old"]:
            old = f"({value['old']}x OLD)"
            olds += value["old"]
        lines.append(f"{value['count']}x {value['name']} ({', '.join(statuses)}) {old}")

    statuses, old = [], ""
    if destroyed:
        statuses.append(f"{destroyed}x DESTROYED")
    if damaged:
        statuses.append(f"{damaged}x DAMAGED")
    if captured:
        statuses.append(f"{captured}x CAPTURED")
    if olds:
        old = f"({olds}x OLD)"

    return lines, f"{total}x ({', '.join(statuses)}) {old}" if total else ""


def render_table(date: str, ru_losses: list[str], ru_total: str, ua_losses: list[str], ua_total: str):
    losses = list(zip_longest(ru_losses, ua_losses, fillvalue="&nbsp;"))
    static_dir = Path(__file__).parent.parent.parent / "static"
    env = jinja2.Environment(loader=jinja2.FileSystemLoader(static_dir))
    template = env.get_template("template.html")
    img = imgkit.from_string(template.render(date=date, losses=losses, ru_total=ru_total, ua_total=ua_total), False)
    return img


async def generate_table(user, client: TelegramClient, config, logger, force_new=False, **context):
    source_id = config.getint("repost", "source_id")
    target_id = context.get("send_to") or config.getint("general", "target_id")
    tz = pytz.timezone(config.get("general", "timezone"))

    gsheet_id = config.get("general", "gsheet_id")
    gsheet_key = config.get("general", "gsheet_key")

    cache_fp = Path(config.get("general", "table_cache_fp"))

    start, end = get_time_range(tz)
    date = start.date().strftime("%d.%m.%Y")
    results: list[Item] = get_cache(cache_fp, date)
    if force_new or not results:
        relevant_posts = []
        async for message in user.iter_messages(source_id):
            if start > message.date:
                break

            if (start <= message.date < end) and message.text:
                # Lets pre-filter archived messages for the sake of my sanity.
                msg_headers = set(word.lower().strip(".,!?/()") for word in message.text.split()[:5])
                if "архив" in msg_headers:
                    continue

                relevant_posts.append(message)

        if not len(relevant_posts):
            logger.info("No relevant posts to process..")
            raise ValueError("No relevant posts to process..")

        logger.info("Grabbed %s relevant posts and processing..", len(relevant_posts))
        extra_prompt = await get_gsheet_prompt(gsheet_id, gsheet_key)

        page_size, sem, tasks = 3, asyncio.Semaphore(8), []
        for page in range(len(relevant_posts[::page_size])):
            page_posts = relevant_posts[page * page_size : (page + 1) * page_size]
            tasks.append(parse_messages([m.raw_text for m in page_posts], extra_prompt, sem))

        results = list(chain(*(await asyncio.gather(*tasks))))
        store_cache(cache_fp, date, results)

    ru_counter = defaultdict(lambda: {"count": 0, "old": 0, "damaged": 0, "destroyed": 0, "captured": 0})
    ua_counter = defaultdict(lambda: {"count": 0, "old": 0, "damaged": 0, "destroyed": 0, "captured": 0})
    for item in results:
        choice = ru_counter if item.ownership == "ru" else ua_counter
        counter = choice[item.name.upper()]
        counter["name"] = item.name.upper().replace(" OBR. ", " obr. ")
        counter["count"] += 1
        counter[item.status] += 1

        if item.post_date:
            now = datetime.now(tz).date()
            post_date = datetime.strptime(item.post_date, "%d.%m.%Y").date()
            counter["old"] += (now - timedelta(days=14)) > post_date

    vehicle_types = await get_vehicle_types(gsheet_id, gsheet_key)
    ru_losses, ru_total = convert_counter_into_lines(ru_counter, vehicle_types)
    ua_losses, ua_total = convert_counter_into_lines(ua_counter, vehicle_types)

    table_img = render_table(date, ru_losses, ru_total, ua_losses, ua_total)
    tg_file = await client.upload_file(table_img, file_name=f"{date}-{token_hex(10)}.jpg")
    caption = f"Згенерована таблиця за {date}\n#table #таблиця"
    return tg_file, caption, target_id, date


def get_next_run_at(tz, hour: int, minute: int):
    now = datetime.now(tz)
    if (now.hour * 60 + now.minute) < (hour * 60 + minute):
        return now.replace(hour=hour, minute=minute)
    return now.replace(hour=hour, minute=minute) + timedelta(days=1)


async def scheduled_table(config, client, user, logger, storage, **context):
    target_id = config.getint("general", "target_id")
    while True:
        tz = pytz.timezone(config.get("general", "timezone"))
        d = datetime.strptime(config.get("general", "table_schedule_at"), "%H:%M")

        delta_time = get_next_run_at(tz, d.hour, d.minute) - datetime.now(tz)
        logger.info(f"Scheduling table generation for {delta_time} ...")
        sleep_until_next = round(delta_time.total_seconds())
        logger.info(f"Sleeping until table generation ({sleep_until_next} seconds) ...")
        await asyncio.sleep(sleep_until_next)

        async for message in user.iter_messages(target_id, filter=InputMessagesFilterPinned):
            if "#table #таблиця" in message.text:
                try:
                    await message.unpin()
                except Exception as e:
                    logger.exception(e)
                    break

        try:
            tg_file, caption, _, date = await generate_table(force_new=True, **storage)
            buttons = [Button.inline("Згенерувати повторно", f"v0|{target_id}|{date}")]
            message = await client.send_file(target_id, tg_file, caption=caption, buttons=buttons)
            await message.pin()
        except Exception as e:
            logger.exception(e)
            await asyncio.sleep(30)


async def init(client: TelegramClient, logger, storage, **context):
    logger.info("Initiating table generator ...")
    callback_lock, callback_cache = asyncio.Lock(), Cache(ttl=60)

    @cached(ttl=60 * 5)
    async def get_channel_admins(channel_id: int):
        admins = await client.get_participants(channel_id, filter=ChannelParticipantsAdmins)
        return set(admin.id for admin in admins)

    # @TODO: Add a button to confirm/uncofirm table automatically post it at
    #   the certain other time to the main channel. Also add limited LLM
    #   chatbot functionality with certain tools to edit table data from chat (?)
    asyncio.create_task(scheduled_table(**storage))

    @client.on(events.NewMessage(pattern="^/table ?(new)?$", func=lambda e: not (e.is_channel and not e.is_group)))
    async def table_generation_handler(event):
        await event.delete()
        force_new = bool(event.pattern_match.group(1))
        logger.info(f"Processing /table command (force_new={force_new}) ...")
        tg_file, caption, target_id, _ = await generate_table(force_new=force_new, send_to=event.chat_id, **storage)
        await client.send_file(target_id, tg_file, caption=caption)

    @client.on(events.CallbackQuery)
    async def callback_query_handler(event):
        async with callback_lock:
            _, channel_id, date = event.data.decode().split("|")

            post_date, now = datetime.strptime(date, "%d.%m.%Y"), datetime.now()
            if (now.replace(tzinfo=None) - post_date) > timedelta(days=3):
                await event.answer("Пост занадто старий для редагування!", alert=True)
                return

            admins = await get_channel_admins(int(channel_id))
            if event.sender_id not in admins:
                await event.answer("You are not an admin, bucko!", alert=True)
                return

            recent = await callback_cache.get("callback_query")
            if recent:
                await event.answer("Почекайте хвилину перед тим як генерувати знову!", alert=True)
                return

            await callback_cache.set("callback_query", True)

        await event.answer("Почекайте хвилину поки генерується таблиця!", alert=True)
        tg_file, _, _, _ = await generate_table(force_new=True, send_to=channel_id, **storage)

        try:
            original_message = await event.get_message()
            await original_message.edit(file=tg_file)
        except MessageNotModifiedError as e:
            logger.info(f"Did not modify the message (identical file): {e}!")
