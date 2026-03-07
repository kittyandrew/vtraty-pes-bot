# @NOTE: This module previously contained TGSpawner with full account creation via SMS activation
# services (sms-activate.org). That functionality was removed — we only log into existing accounts
# now. The old code is preserved in git history if ever needed again.

import telethon


class BadAccountError(Exception):
    """Raised when a session file exists but the account is not authorized."""


class TGSpawner:
    def __init__(self, tg_api_hash: str, tg_api_id: str, path: str, logger=None):
        self.tg_api_hash = tg_api_hash
        self.tg_api_id = tg_api_id
        self.path = path
        self.logger = logger

    async def load_account(self):
        """Load an existing session file and verify the account is authorized."""
        client = telethon.TelegramClient(
            session=self.path,
            api_hash=self.tg_api_hash,
            api_id=self.tg_api_id,
        )
        await client.connect()

        if not await client.is_user_authorized():
            clean = await client.log_out()
            assert clean, "Log out is broken!"
            raise BadAccountError

        return client

    async def login(self, **kwargs):
        """Interactive login — prompts for phone/code (or uses bot_token kwarg)."""
        client = telethon.TelegramClient(
            session=self.path,
            api_hash=self.tg_api_hash,
            api_id=self.tg_api_id,
        )
        await client.start(**kwargs)
        return client
