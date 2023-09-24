from datetime import datetime, timedelta
from pyppeteer import launch
from pathlib import Path
from time import time
import logging
import asyncio
import pytz
import cv2
import re


class BrowserManager:
    SAVELIFEINUA_URL = "https://savelife.in.ua/reporting/"
    TABLE_ITEM = "//table[contains(@class, 'income-donation-table')]/tbody/tr"
    COMMENT_RE = re.compile(r"\(([\d\.]+) ([a-zA-Z]+)\)")

    def __init__(self, max_pages: int = 2, logger = logging):
        self.logger = logger

        self.browser = None
        self.browser_lock = asyncio.Lock()

        self.open_pages = 0
        self.pages_sem = asyncio.Semaphore(max_pages)

    async def __aenter__(self):
        async with self.browser_lock:
            if not self.browser:
                self.browser = await launch(
                    executablePath="/usr/bin/google-chrome-stable",
                    headless=True, args=["--no-sandbox"]
                )
                self.logger.info("Created new browser ...")

        return self.browser

    async def __aexit__(self, exc_type, exc, tb):
        assert self.browser
        if not self.open_pages:
            await self.browser.close()
            self.browser = None
            self.logger.info("Closed existing browser ...")

    async def track_savelifeinua_donation(self, amount, workdir: Path):
        async with self as browser, self.pages_sem:
            page = await browser.newPage()
            await page.setViewport({"height": 5000, "width": 1000}) # @TODO: explain
            await page.goto(self.SAVELIFEINUA_URL)

            self.open_pages += 1
            self.logger.info("Spawned a page for the job (%s total) ...", self.open_pages)
            try:
                return await self._track(page, amount, workdir)
            finally:
                await page.close()
                self.open_pages -= 1

    @staticmethod
    def underscore_donation(input_fp: str, output_fp: str, dy, dh):
        source = cv2.imread(input_fp)
        dw = source.shape[1]

        color, thickness, delta_x, delta_y = (3, 125, 80), 2, 5, 10
        p1, p2 = (delta_x, int(dy + dh - delta_y)), (int(dw - delta_x), int(dy + dh - delta_y))
        donation = cv2.line(source, p1, p2, color, thickness)

        cv2.imwrite(output_fp, donation)

    async def _track(self, page, amount, workdir: Path):
        self.logger.info("Tracking reports from '%s' for amount '%s' ...", self.SAVELIFEINUA_URL, amount)
        # Look for donation for the next 30 minutes.
        start, scan_time = time(), 60 * 30
        while (time() - start) < scan_time:
            await page.waitForXPath(self.TABLE_ITEM)
            elements = await page.xpath(self.TABLE_ITEM)
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

                print(comment)
                comment_match = self.COMMENT_RE.search(comment)
                assert comment_match

                donation_size = float(comment_match.group(1))
                print(donation_size, amount, donation_size == amount)
                if donation_size != amount: continue

                tmp_fp, output_fp = workdir / "raw_donation.png", workdir / "donation.png"
                self.logger.info("Found donation for '%s' [%s]. Saving screenshot to '%s' ...", amount, date_text, tmp_fp)
                rect = await element.boundingBox()
                width, height, coeff_w_to_h = rect["width"], rect["height"], 3
                rect["height"] =  width / coeff_w_to_h
                rect["y"] -= (rect["height"] - height) / 2

                await page.screenshot({"path": tmp_fp, "clip": rect})
                self.logger.info("Altering screenshot, reading from '%s', writing to '%s' ...", tmp_fp, output_fp)
                self.underscore_donation(str(tmp_fp), str(output_fp), (rect["height"] - height) / 2, height)
                return True, output_fp

            await asyncio.sleep(20)
            await page.reload()

        return False, None


if __name__ == "__main__":
    logging.basicConfig(
        format="%(asctime)s - %(filename)s - %(levelname)s - %(message)s",
        datefmt="%d-%b-%y %H:%M:%S", level=logging.INFO
    )
    async def main(workdir = Path(".")):
        manager = BrowserManager()
        res = await manager.track_savelifeinua_donation(50, workdir)
        print("RES:", res)
    asyncio.get_event_loop().run_until_complete(main())

