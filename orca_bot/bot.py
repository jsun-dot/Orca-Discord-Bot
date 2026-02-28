import asyncio
import datetime
import logging
import os
from pathlib import Path

import discord
from discord.ext import commands

from orca_bot.utils.views import NowPlayingButtons

# Load environment variables from a local .env file if python-dotenv is installed
try:
    from dotenv import load_dotenv  # type: ignore

    load_dotenv()
except Exception:
    pass

PACKAGE_ROOT = Path(__file__).resolve().parent
COGS_DIR = PACKAGE_ROOT / "cogs"


def _get_discord_token() -> str:
    token = os.getenv("DISCORD_TOKEN")
    if not token:
        raise RuntimeError("Missing DISCORD_TOKEN. Put it in your environment or in a .env file in the project root.")
    return token

# basic Discord Bot Necessities
intents = discord.Intents.all()
intents.members = True
client = commands.Bot(command_prefix="`", intents=intents, help_command=None)
_persistent_views_registered = False

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
logger.propagate = False

if not logger.handlers:
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)

    current_date = datetime.date.today().strftime("%Y-%m-%d")
    log_file = f"log_{current_date}.txt"
    file_handler = logging.FileHandler(filename=log_file, mode="a")
    file_handler.setLevel(logging.INFO)

    formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
    console_handler.setFormatter(formatter)
    file_handler.setFormatter(formatter)

    logger.addHandler(console_handler)
    logger.addHandler(file_handler)

async def load():
    loaded_cogs = 0
    failed_cogs = []
    for path in sorted(COGS_DIR.glob("*.py")):
        if path.name == "__init__.py":
            continue

        extension = f"orca_bot.cogs.{path.stem}"
        try:
            await client.load_extension(extension)
            loaded_cogs += 1
        except Exception as exc:
            logger.error(f"Failed to load extension {path.name}: {exc}")
            failed_cogs.append(path.name)
    logger.info(f"Loaded {loaded_cogs} cogs successfully.")
    if failed_cogs:
        logger.warning(f"Failed to load {len(failed_cogs)} cog(s): {', '.join(failed_cogs)}")
    else:
        logger.info("All cogs loaded successfully.")

async def main():
    global _persistent_views_registered

    if not _persistent_views_registered:
        client.add_view(NowPlayingButtons())
        _persistent_views_registered = True

    for attempt in range(2):
        try:
            await load()
            await client.start(_get_discord_token())
        except Exception as exc:
            logger.error(f"Failed to start bot: {exc}")
            if attempt == 0:
                logger.info("Retrying...")
            else:
                logger.error("Failed to load again. Check the server and restart.")
                break


def run() -> None:
    asyncio.run(main())


if __name__ == "__main__":
    run()
