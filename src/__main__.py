import argparse
import asyncio
import logging
import os
from configparser import ConfigParser

from telethon.errors.rpcerrorlist import PeerFloodError, UserDeactivatedBanError

from .browser_manager import BrowserManager
from .new_account import BadAccountError, TGSpawner
from .tmodules import init as tinit

exists = lambda p: os.path.exists(p)


def main(cpath: str, login: bool = True, new_acc: bool = False):
    loop = asyncio.get_event_loop()

    config = ConfigParser()
    config.read(cpath)

    async def _main(config):
        debug = config.getboolean("general", "debug")

        # Logging:
        logging.basicConfig(
            format="%(asctime)s - %(filename)s - %(levelname)s - %(message)s",
            datefmt="%d-%b-%y %H:%M:%S",
            level=logging.DEBUG if debug else logging.INFO,
        )
        # Separate Telethon logger, it has too much useless logs on info, so we set it to 'warning' level.
        t_logger = logging.getLogger("Telethon Logger")
        t_logger.setLevel(logging.WARNING)
        # Main logger that will be used everywhere in the program.
        logger = logging.getLogger("beehive-bee")

        browser = BrowserManager(logger=logger)
        context = dict(logger=logger, config=config, browser=browser)
        context["storage"] = context  # Self-reference.

        session_path = config.get("general", "session")
        spawner = TGSpawner(
            tg_api_hash=config.get("telegram", "api_hash"),
            tg_api_id=config.get("telegram", "api_id"),
            sms_api_key=config.get("simservice", "api_key", fallback=""),
            name=config.get("user", "name", fallback=""),
            username=config.get("user", "username", fallback=None),
            # profile_picture = config.get("user", "image"),
            channels_to_join=config.get("user", "channels", fallback="").split(","),
            path=session_path,
            logger=logger,
        )

        if new_acc:
            await spawner.get_new_account()
            exit(0)

        if login:
            bot_token = config.get("telegram", "token", fallback=None)
            await spawner.login(token=bot_token)
            exit(0)

        if not exists(session_path):
            print(f"Session file '{session_path}' is missing!")
            exit(1)

        client, _ = await spawner.load_account()
        context["client"] = client

        await tinit(**context)
        logging.info("Initiation completed ...")

    loop.run_until_complete(_main(config))
    try:
        loop.run_forever()
    finally:
        loop.stop()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=str, default="config.ini", help="Path to the config file.")
    parser.add_argument(
        "--login", action=argparse.BooleanOptionalAction, default=False, help="Instead of starting the application, log in."
    )
    parser.add_argument(
        "--new", action=argparse.BooleanOptionalAction, default=False, help="Instead of starting the application, sign up."
    )
    args = parser.parse_args()

    if not exists(args.config):
        print(f"Config file doesn't exist [path '{args.config}']!")
        exit(1)

    main(args.config, args.login, args.new)
