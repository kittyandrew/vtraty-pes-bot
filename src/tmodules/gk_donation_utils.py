from datetime import datetime, timedelta
from pathlib import Path
from time import time
import logging
import asyncio
import pytz
import cv2
import re

# General config.
SAVELIFEINUA_URL = "https://savelife.in.ua/reporting/"
TABLE_ITEM = "//table[contains(@class, 'income-donation-table')]/tbody/tr"
COMMENT_RE = re.compile(r"\((\d+) ([a-zA-Z]+)\)")


def underscore_donation(input_fp: str, output_fp: str, dy, dh):
    source = cv2.imread(input_fp)
    dw = source.shape[1]

    color, thickness, delta_x, delta_y = (3, 125, 80), 2, 5, 10
    p1, p2 = (delta_x, int(dy + dh - delta_y)), (int(dw - delta_x), int(dy + dh - delta_y))
    donation = cv2.line(source, p1, p2, color, thickness)

    cv2.imwrite(output_fp, donation)


async def track_savelifeinua_donation(browser, amount, workdir: Path, logger = logging):
    page = await browser.newPage()
    await page.setViewport({"height": 5000, "width": 1000}) # @TODO: explain
    logger.info("Tracking reports from '%s' for amount '%s' ...", SAVELIFEINUA_URL, amount)
    await page.goto(SAVELIFEINUA_URL)

    # Look for donation for the next 30 minutes.
    start, scan_time = time(), 60 * 30
    while (time() - start) < scan_time:
        await page.waitForXPath(TABLE_ITEM)
        elements = await page.xpath(TABLE_ITEM)
        for element in elements:
            date_elements = await element.xpath("./td[contains(@data_label, 'Дата, час')]")
            assert len(date_elements) == 1

            date_text_handle = await date_elements[0].getProperty("innerText")
            date_text = await date_text_handle.jsonValue()

            # @TODO: Pass in 'timezone' from config.
            timezone = pytz.timezone("Europe/Kyiv")
            donation_date = datetime.strptime(date_text.strip(" \r\t\n"), "%d.%m.%Y, %H:%M").replace(tzinfo=timezone)
            now, donation_delta = datetime.now(timezone), timedelta(hours=1)
            # @TODO: This shit is broken somehow...
            # if (now - donation_date) > donation_delta: break

            # @NOTE: There are 2 places in the table where each donated sum is shown. First, lets check
            #        the 'comment' section and not the obvious 'donation sum' section, because comment
            #        seems to show a sum before transactional or any other additional costs, so it's more
            #        likely to be matching what person actually spent when making a donation, versus what
            #        'savelife.in.ua' actually received on their end).
            comment_elements = await element.xpath("./td[contains(@data_label, 'Коментар')]")
            assert len(comment_elements) == 1
            comment_handle = await comment_elements[0].getProperty("innerText")
            comment = await comment_handle.jsonValue()

            comment_match = COMMENT_RE.search(comment)
            assert comment_match

            donation_size = float(comment_match.group(1))
            if donation_size != amount: continue

            tmp_fp, output_fp = workdir / "raw_donation.png", workdir / "donation.png"
            logger.info("Found donation for '%s' [%s]. Making screenshot and saving to '%s' ...", amount, date_text, tmp_fp)
            rect = await element.boundingBox()
            width, height, coeff_w_to_h = rect["width"], rect["height"], 3
            rect["height"] =  width / coeff_w_to_h
            rect["y"] -= (rect["height"] - height) / 2

            await page.screenshot({"path": tmp_fp, "clip": rect})
            logger.info("Altering screenshot, reading from '%s', writing to '%s' ...", tmp_fp, output_fp)
            underscore_donation(str(tmp_fp), str(output_fp), (rect["height"] - height) / 2, height)

            await page.close()
            return True, output_fp

        await asyncio.sleep(20)
        await page.reload()

    await page.close()
    return False, None


if __name__ == "__main__":
    logging.basicConfig(
        format="%(asctime)s - %(filename)s - %(levelname)s - %(message)s",
        datefmt="%d-%b-%y %H:%M:%S", level=logging.INFO
    )
    async def main():
        browser = await launch(executablePath="/usr/bin/google-chrome-stable", headless=True)
        # browser = await launch(executablePath="/usr/bin/google-chrome-stable", headless=True, args=["--no-sandbox"])

        amount = 51
        await track_savelifeinua_donation(browser, amount, Path("."))
        await browser.close()
    asyncio.get_event_loop().run_until_complete(main())

