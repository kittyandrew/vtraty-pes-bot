from telethon.tl.functions.photos import UploadProfilePhotoRequest
from telethon.tl.functions.account import UpdateUsernameRequest
from telethon.tl.functions.channels import JoinChannelRequest
import telethon
import aiohttp
import asyncio
import random
import ujson
import os

exists = lambda p: os.path.exists(p)


class GenericCreationError(Exception):
    """Generic error"""
    def __init__(self, client, task_id, message="Failed to create a new account!"):
        self.client = client
        self.task_id = task_id
        self.message = message
        super().__init__(self.message)



class BadAccountError(Exception):
    """An error indicating that account needs to be recreated"""


class TGSpawner:
    # DEFAULT_SMS_URL = "https://sms-activate.ru/stubs/handler_api.php"
    DEFAULT_SMS_URL = "https://api.sms-activate.org/stubs/handler_api.php"

    def __init__(
        self, tg_api_hash: str, tg_api_id: str, sms_api_key: str, sms_api_url: str = DEFAULT_SMS_URL,
        name: str = "Guy", username: str = None, profile_picture: str = "", channels_to_join: list[str] = None,
        path: str = None, logger = None, ecallback = None,
    ):
        self.tg_api_hash = tg_api_hash
        self.tg_api_id = tg_api_id

        self.sms_api_key = sms_api_key
        self.sms_api_url = sms_api_url

        self.name = name
        self.username = username
        self.profile_picture = profile_picture

        self.channels_to_join = channels_to_join or []

        self.path = path
        self.logger = logger

        self.ecallback = ecallback

    async def get(self, action: str, params: dict = {}):
        params["action"] = action
        params["api_key"] = self.sms_api_key
        async with aiohttp.ClientSession() as session:
            async with session.get(self.sms_api_url, params=params) as r:
                t = await r.text()
                if not t:
                    raise ValueError("Empty response..")

                try:
                    return ujson.loads(t)
                except ValueError:
                    return t

    async def get_countries(self):
        r = await self.get("getCountries")
        return r

    # TODO: 'expensive_first' is a suboptimal mode, which forces the most expensive phone numbers,
    #       but since ~mid-2022 there are major issues trying to use cheaper numbers, because
    #       error rate is >99% (maybe some major spam-propaganda bot orgs picked it up).
    #       With 'expensive_first' boolean set to True, success rate is fairly high which makes
    #       the script usable. Might try to play with the price and look for middle price or smth.
    async def get_best(self, offset: int = 0, ignore: list[int] = None, expensive_first = False):
        r = await self.get("getTopCountriesByService", {"service": "tg"})
        best_prices = sorted(list(r.values()), key=lambda o: o["price"])
        if expensive_first:
            best_prices = reversed(best_prices)

        def best_filter(o):
            if ignore:  return o["country"] not in ignore
            return o["count"] > 100

        best_options = filter(best_filter, best_prices)
        # Skip offset:
        for _ in range(offset):
            next(best_options)

        return next(best_options)

    async def get_balance(self):
        r = await self.get("getBalance", {})
        _, amount = r.split(":")
        return float(amount)

    async def get_new_account(self):
        context = {"ignore": [10], "offset": 0, "attempts": 0}
        # Avoiding recursion:
        while True:
            try:
                return await self._get_new_account(context)
            except GenericCreationError as e:
                # Clean up before trying again:
                self.logger.error("Task %s failed! Cleaning up and starting another task.", e.task_id)
                clean = await e.client.log_out()
                assert clean, "Log out is broken!"

    async def _get_new_account(self, context):
        while True:
            best_option = await self.get_best(context["offset"], context["ignore"], expensive_first = True)
            context["attempts"] += 1

            # Ignore country after few tries.
            if context["attempts"] >= 2:
                context["attempts"] = 0
                context["ignore"].append(best_option["country"])
                continue

            r = await self.get("getNumber", {"service": "tg", "country": best_option["country"]})
            if r == "NO_BALANCE":
                self.logger.fatal("You don't have enough balance to continue with user '%s'.", i)
                raise RuntimeError("Not enough balance!")

            elif r == "NO_NUMBERS":
                self.logger.info("Country with an ID %s ran out of numbers! Moving to the next one (more expensive).", best_option["country"])
                context["offset"] += 1
                continue

            break

        _, task_id, phone = r.split(":")

        client = telethon.TelegramClient(
            session=self.path,
            api_hash=self.tg_api_hash,
            api_id=self.tg_api_id,
            update_error_callback=self.ecallback,
        )
        await client.connect()

        if await client.is_user_authorized():
            self.logger.debug("Phone %s was already authorized. Early return...", phone)
            return client, phone

        try:
            await client.sign_in(phone)
        except telethon.errors.rpcerrorlist.PhoneNumberInvalidError:
            self.logger.info("Number %s is invalid!", phone)
            raise GenericCreationError(client, task_id)
        except telethon.errors.rpcerrorlist.PhoneNumberBannedError:
            self.logger.info("Number %s is banned!", phone)
            raise GenericCreationError(client, task_id)
        except telethon.errors.rpcerrorlist.FloodWaitError:
            self.logger.info("Number %s is flood-limited!", phone)
            raise GenericCreationError(client, task_id)

        self.logger.debug("[Task %s]: Polling for sms for +%s ...", task_id, phone)
        code = None
        # max_wait = 40
        max_wait = 60
        sleep_for = 8
        ok_prefix = "STATUS_OK:"

        while max_wait:
            r = await self.get("getStatus", {"id": task_id})
            self.logger.debug("[Task %s]: status %s ...", task_id, r)
            if r.startswith(ok_prefix):
                code = r.removeprefix(ok_prefix)
                break

            max_wait -= sleep_for
            await asyncio.sleep(sleep_for)

        # Failed to sign up/in, which means we need to clean up and try again.
        if not code:
            raise GenericCreationError(client, task_id)

        try:
            await client.sign_in(code=code)
            self.logger.info("[Task %s]: Successfully signed-in into existing account!", task_id)

            assert False, "This is a weird edge case..."
        except Exception as e:
            try:
                await client.sign_up(code, self.name)
            except telethon.errors.rpcerrorlist.SessionPasswordNeededError:
                self.logger.info("Logged in but password required (2FA prbbly)!", phone)
                raise GenericCreationError(client, task_id)

            self.logger.info("[Task %s]: Created a user with a name '%s' ...", task_id, self.name)

            if self.username:
                try:
                    result = await client(UpdateUsernameRequest(username=self.username))
                except Exception as e:
                    self.logger.error(e)
                    exit(1)  # @nocheckin

                self.logger.info("[Task %s]: Successfully set username to '@%s'!", task_id, self.username)

            # If set up, update profile with a given picture.
            if self.profile_picture:
                assert exists(self.profile_picture), "File path for PP is provided but it wasn't found!"
                await client(UploadProfilePhotoRequest(
                    await client.upload_file(self.profile_picture)
                ))
                self.logger.info("[Task %s]: Uploaded image '%s' and set as profile picture ...", task_id, self.profile_picture)

            # After performing profile changes, join required channels:
            for username in self.channels_to_join:
                channel = await client.get_entity(username)
                await client(JoinChannelRequest(channel))
                self.logger.info("[Task %s]: Joined a channel '%s' ...", task_id, username)

        # TODO: Trigger 'BadAccountError' here? Does that even make sense?
        assert await client.is_user_authorized()
        return client, phone

    async def load_account(self):
        client = telethon.TelegramClient(
            session=self.path,
            api_hash=self.tg_api_hash,
            api_id=self.tg_api_id,
            # update_error_callback=self.ecallback,
        )
        await client.connect()

        # Check if account is broken and raise if necessary.
        if not await client.is_user_authorized():
            clean = await client.log_out()
            assert clean, "Log out is broken!"

            raise BadAccountError

        # TODO: Get phone number
        return client, None

    async def login(self, token: str = None):
        client = telethon.TelegramClient(
            session=self.path,
            api_hash=self.tg_api_hash,
            api_id=self.tg_api_id,
            # update_error_callback=self.ecallback,
        )
        await client.start(bot_token=token)
        return client

