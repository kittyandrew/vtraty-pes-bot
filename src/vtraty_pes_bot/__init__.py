import argparse
import asyncio
import logging
import os
from configparser import ConfigParser

from .new_account import TGSpawner
from .tmodules import init as tinit


def main(cpath: str, login=False, user_login=False):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

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

        context = dict(logger=logger, config=config)
        context["storage"] = context  # Self-reference.

        api_hash = config.get("telegram", "api_hash")
        api_id = config.get("telegram", "api_id")

        session_path = config.get("general", "session")
        spawner = TGSpawner(tg_api_hash=api_hash, tg_api_id=api_id, path=session_path, logger=logger)

        if login:
            bot_token = config.get("telegram", "token", fallback=None)
            await spawner.login(bot_token=bot_token)
            exit(0)

        if not os.path.exists(session_path):
            print(f"Session file '{session_path}' is missing!")
            exit(1)

        context["client"] = await spawner.load_account()

        user_session_path = config.get("general", "user_session")
        spawner = TGSpawner(tg_api_hash=api_hash, tg_api_id=api_id, path=user_session_path, logger=logger)

        if user_login:
            await spawner.login()
            exit(0)

        if not os.path.exists(user_session_path):
            print(f"Session file '{user_session_path}' is missing!")
            exit(1)

        context["user"] = await spawner.load_account()

        await tinit(**context)
        logging.info("Initiation completed ...")

    loop.run_until_complete(_main(config))
    try:
        loop.run_forever()
    finally:
        loop.stop()
        loop.close()


def main_cli():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--config",
        type=str,
        required=True,
        help="Path to the config file.",
    )
    parser.add_argument(
        "--login",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Instead of starting the application, log in.",
    )
    parser.add_argument(
        "--user-login",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Instead of starting the application, log your user account in.",
    )
    args = parser.parse_args()

    if not os.path.exists(args.config):
        print(f"Config file doesn't exist [path '{args.config}']!")
        exit(1)

    return main(args.config, args.login, args.user_login)
