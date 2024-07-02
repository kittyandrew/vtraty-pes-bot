import asyncio
import logging
import tempfile
from pathlib import Path
from pprint import pprint
from typing import Union

import cv2
from moviepy.editor import *
from PIL import Image, ImageDraw, ImageFont
from telethon import events
from telethon.tl.types import ChannelParticipantsAdmins


def watermark_video(
    workdir: Path,
    filename_in: Union[str, Path],
    filename_out: Union[str, Path],
    logo_path: Union[str, Path],
    logger=logging,
    heavy_debug: bool = False,
):
    fp_in = str(workdir / filename_in)
    fp_out_intermediate = str(workdir / "silent_output.mp4")
    fp_out = str(workdir / filename_out)

    # Creating input video reader.
    cap = cv2.VideoCapture(fp_in)
    # Reading input video dimentions, frames etc:
    fourcc, fps = cv2.VideoWriter_fourcc(*"MP4V"), int(cap.get(cv2.CAP_PROP_FPS))
    HEIGHT, WIDTH = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)), int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    # Creating intermediate output video writer.
    out = cv2.VideoWriter(fp_out_intermediate, fourcc, fps, (WIDTH, HEIGHT))

    original_logo = cv2.imread(str(logo_path), cv2.IMREAD_UNCHANGED)
    LOGO_H, LOGO_W = original_logo.shape[:2]
    REL_LOGO_SIZE = 2.5 if WIDTH > 800 else 2 if WIDTH > 500 else 1
    REL_PROP = round(WIDTH / REL_LOGO_SIZE / LOGO_W, 2)
    LOGO_H, LOGO_W = int(LOGO_H * REL_PROP), int(LOGO_W * REL_PROP)
    print(REL_LOGO_SIZE, REL_PROP, LOGO_H, LOGO_W)
    logo = cv2.resize(original_logo, (LOGO_W, LOGO_H), interpolation=cv2.INTER_CUBIC)

    x, y, dx, dy = (WIDTH - LOGO_W) // 2, (HEIGHT - LOGO_H) // 2, WIDTH // 100, HEIGHT // 100
    frame_count = 0

    logger.info("Starting to process video '%s' ('%s') ...", fp_in, fp_out)
    while True:
        success, frame = cap.read()
        if not success:
            break

        if (x < abs(dx)) or (x > (WIDTH - logo.shape[1] - dx)):
            dx *= -1
        if (y < abs(dy)) or (y > (HEIGHT - logo.shape[0] - dy)):
            dy *= -1

        x += dx if REL_LOGO_SIZE != 1 else 0
        y += dy

        frame_count += 1
        if heavy_debug:
            logger.debug("Frame #%-5s (x = %-4s y = %-4s) ...", frame_count, x, y)

        overlay = frame.copy()

        y1, y2 = y, y + logo.shape[0]
        x1, x2 = x, x + logo.shape[1]

        alpha = 0.5
        a1 = logo[:, :, 3] / 255.0
        a2 = 1.0 - a1

        for c in range(0, 3):
            overlay[y1:y2, x1:x2, c] = a1 * logo[:, :, c] + a2 * overlay[y1:y2, x1:x2, c]

        new_frame = cv2.addWeighted(overlay, alpha, frame, 1 - alpha, 0)

        out.write(new_frame)
        if heavy_debug:
            cv2.imshow("preview", new_frame)
            if cv2.waitKey(1) & 0xFF == ord("s"):
                break

    if heavy_debug:
        cv2.destroyAllWindows()
    cap.release()
    out.release()
    logger.info("Done with processing video '%s' ('%s')! Cloning audio...", fp_in, fp_out)

    in_video = VideoFileClip(fp_in)
    out_video = VideoFileClip(fp_out_intermediate)
    if in_video.audio:
        out_video.audio = CompositeAudioClip([in_video.audio])
        logger.info("Done processing audio for video '%s' ('%s')! Finished.", fp_in, fp_out)
    else:
        logger.info("No audio detected! Finished '%s' ('%s').", fp_in, fp_out)
    out_video.write_videofile(fp_out)
    return fp_out


def get_dynamic_size_font(height: int, text: str):
    size = 0
    while True:
        size += 1
        font = ImageFont.load_default(size)
        rect = font.getbbox(text)
        t_hi = rect[2] - rect[0]
        if (t_hi / height) > 0.9:
            return font, size


def draw_shade(draw, x, y, delta, text, fill, font, swidth, spacing):
    draw.text((x - delta, y - delta), text, fill, font, stroke_width=swidth, spacing=spacing)
    draw.text((x + delta, y - delta), text, fill, font, stroke_width=swidth, spacing=spacing)
    draw.text((x - delta, y + delta), text, fill, font, stroke_width=swidth, spacing=spacing)
    draw.text((x + delta, y + delta), text, fill, font, stroke_width=swidth, spacing=spacing)


def watermark_image(
    workdir: Path,
    filename_in: Union[str, Path],
    filename_out: Union[str, Path],
    logo_path: Union[str, Path],
    logger=logging,
    heavy_debug: bool = True,
):
    fp_in = str(workdir / filename_in)
    fp_out = str(workdir / filename_out)

    background = Image.open(fp_in)
    swidth = 3 if background.height > 500 else 1
    # foreground = Image.open(logo_path)
    # mask = foreground.copy()
    # mask.putalpha(64)

    # background.paste(foreground, (0, 0), mask)
    # font = ImageFont.truetype("data/serif-regular.ttf", 40)

    text = "t.me/lost_warinua"
    # text = "@lost_warinua"
    font, fsize = get_dynamic_size_font(background.height, text)
    rect = font.getbbox(text)
    hi, wi = rect[2] - rect[0], rect[3] - rect[1] + fsize / 4
    x, y = int((background.width - wi) / 2), int((background.height - hi) / 2)

    # Drawing multiple watermarks.
    c = 255
    delta = wi + 25
    margin_x = -delta
    for _ in range(3):
        z = 10
        watermark = background.crop((int(x + margin_x) - z, y - z, int(x + wi + margin_x) + z, y + hi + z))
        watermark = watermark.rotate(90, expand=1)
        draw_watermark = ImageDraw.Draw(watermark)
        watermark.putalpha(0)
        draw_shade(draw_watermark, z, z, z, text, (c, c, c, 20), font, swidth, spacing=1)
        draw_shade(draw_watermark, z, z, 9, text, (c, c, c, 35), font, swidth, spacing=1)
        draw_shade(draw_watermark, z, z, 8, text, (c, c, c, 50), font, swidth, spacing=1)
        draw_shade(draw_watermark, z, z, 7, text, (c, c, c, 65), font, swidth, spacing=1)
        draw_shade(draw_watermark, z, z, 6, text, (c, c, c, 80), font, swidth, spacing=1)
        draw_shade(draw_watermark, z, z, 5, text, (c, c, c, 95), font, swidth, spacing=1)
        draw_shade(draw_watermark, z, z, 4, text, (c, c, c, 110), font, swidth, spacing=1)
        draw_shade(draw_watermark, z, z, 3, text, (c, c, c, 125), font, swidth, spacing=1)
        draw_shade(draw_watermark, z, z, 2, text, (c, c, c, 140), font, swidth, spacing=1)
        draw_shade(draw_watermark, z, z, 1, text, (c, c, c, 155), font, swidth, spacing=1)
        draw_watermark.text((z, z), text, (c, c, c, 250), font, stroke_width=swidth, spacing=1)
        watermark = watermark.rotate(270, expand=1)
        background.paste(watermark, (int(x + margin_x), y), watermark)
        margin_x += delta

    background.save(fp_out)
    return fp_out


async def init(client, logger, config, **context):
    logo_admins = [int(la) for la in config.get("general", "logo_users").split(",")]
    logo_fp = config.get("general", "logo")
    # target_id = config.getint("general", "target_id")

    logger.info("Initiating watermark maker ...")

    @client.on(events.NewMessage(pattern=r"^/watermark"))
    async def watermark_maker(event):
        if event.is_channel and not event.is_group:
            return
        if (not hasattr(event, "sender_id")) or (event.sender_id not in logo_admins):
            return

        new_event = await event.get_reply_message()
        if not new_event:
            await event.reply("Couldn't retreive a reply message!")
            return

        event = new_event

        # if not (event.photo or event.video or event.gif):
        if not (event.photo or event.video):
            await event.reply("Reply doesn't have supported media!")
            return

        # if event.video or event.gif: pe = await event.reply("Downloading file...")
        if event.video:
            pe = await event.reply("Downloading file...")
        else:
            pe = None

        with tempfile.TemporaryDirectory() as output_dir:
            workdir = Path(output_dir)
            fp_in = await event.download_media(output_dir)
            if pe:
                await pe.edit("Processing file...")

            # A mess.
            *_, full_filename = fp_in.split("/")
            *filename, ext = full_filename.split(".")
            filename = ".".join(filename)
            output_filename = f"{filename}_watermark.{ext}"

            # @TODO: Add async worker.
            if event.photo:
                force_document = False
                fp_out = watermark_image(workdir, fp_in, output_filename, logo_fp)
            # elif event.video or event.gif:
            elif event.video:
                force_document = True
                fp_out = watermark_video(workdir, fp_in, output_filename, logo_fp)
            else:
                raise

            if pe:
                await pe.edit("Uploading file...")
            tg_file = await event.client.upload_file(fp_out)
            await event.reply(file=tg_file, force_document=force_document)

        if pe:
            await pe.delete()


if __name__ == "__main__":
    debug = False
    logging.basicConfig(
        format="%(asctime)s - %(filename)s - %(levelname)s - %(message)s",
        datefmt="%d-%b-%y %H:%M:%S",
        level=logging.DEBUG if debug else logging.INFO,
    )

    cwd = Path(".")
    # watermark_video(cwd, "source.mp4", "output.mp4", "logo.png", heavy_debug = debug)
    watermark_image(cwd, "source2.jpg", "output2.jpg", "logo.png")
