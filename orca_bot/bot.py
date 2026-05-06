"""Entrypoint and runtime setup for the Orca Discord bot."""

import asyncio
import contextlib
import datetime
import logging
import os
from pathlib import Path
import sys
import threading
from dataclasses import dataclass

import discord
from discord.ext import commands

from orca_bot.utils.views import NowPlayingButtons

PACKAGE_ROOT = Path(__file__).resolve().parent
COGS_DIR = PACKAGE_ROOT / "cogs"
ENV_RUNTIME_PROFILE = "ORCA_PROFILE"
DEFAULT_TOKEN_ENV_VAR = "DISCORD_TOKEN"
DEV_TOKEN_ENV_VAR = "BOT_TOKEN_DEV"
DEFAULT_PROFILE = "default"
DEV_PROFILE = "dev"
COMMAND_PREFIX = "`"
COG_INIT_FILE = "__init__.py"
LOG_LEVEL = logging.INFO
LOG_FORMAT = "%(asctime)s - %(levelname)s - %(message)s"
LOG_DATE_FORMAT = "%Y-%m-%d"
LOG_FILE_TEMPLATE = "log_{date}.txt"
STARTUP_RETRY_ATTEMPTS = 2
CONSOLE_PROMPT = "orca> "
CONSOLE_HELP_TEXT = (
    "Console commands:\n"
    "  help      Show available console commands.\n"
    "  status    Show bot runtime status.\n"
    "  exit      Stop the bot and exit the process.\n"
    "  restart   Restart the bot process."
)
HELP_COMMANDS = frozenset({"help", "?"})
STATUS_COMMANDS = frozenset({"status"})
EXIT_COMMANDS = frozenset({"exit", "quit", "stop"})
RESTART_COMMANDS = frozenset({"restart", "reboot"})

try:
    from dotenv import load_dotenv  # type: ignore

    load_dotenv()
except Exception:
    pass


def _resolve_runtime_credentials() -> tuple[str, str]:
    """
    Return the selected runtime profile and Discord token.

    Raises:
        RuntimeError: If the configured profile is invalid or no token exists
            for the selected runtime profile.
    """

    requested_profile = os.getenv(ENV_RUNTIME_PROFILE, "").strip().lower()
    default_token = os.getenv(DEFAULT_TOKEN_ENV_VAR)
    dev_token = os.getenv(DEV_TOKEN_ENV_VAR)

    if requested_profile:
        if requested_profile == DEV_PROFILE:
            if not dev_token:
                raise RuntimeError(
                    f"{ENV_RUNTIME_PROFILE}={DEV_PROFILE} but "
                    f"{DEV_TOKEN_ENV_VAR} is missing. Put it in your "
                    "environment or in a .env file in the project root."
                )
            return DEV_PROFILE, dev_token

        if requested_profile == DEFAULT_PROFILE:
            if not default_token:
                raise RuntimeError(
                    f"{ENV_RUNTIME_PROFILE}={DEFAULT_PROFILE} but "
                    f"{DEFAULT_TOKEN_ENV_VAR} is missing. Put it in your "
                    "environment or in a .env file in the project root."
                )
            return DEFAULT_PROFILE, default_token

        raise RuntimeError(
            f"Invalid {ENV_RUNTIME_PROFILE}. Use "
            f"'{DEFAULT_PROFILE}' or '{DEV_PROFILE}'."
        )

    if dev_token:
        return DEV_PROFILE, dev_token

    if default_token:
        return DEFAULT_PROFILE, default_token

    raise RuntimeError(
        f"Missing {DEFAULT_TOKEN_ENV_VAR} or {DEV_TOKEN_ENV_VAR}. Put one in "
        "your environment or in a .env file in the project root."
    )


intents = discord.Intents.all()
intents.members = True
client = commands.Bot(
    command_prefix=COMMAND_PREFIX,
    intents=intents,
    help_command=None,
)
_persistent_views_registered = False


@dataclass
class RuntimeCommandState:
    """Track console-command requests for the active bot runtime."""

    profile: str
    stop_requested: bool = False
    restart_requested: bool = False


def _configure_logger() -> logging.Logger:
    """Configure and return the package-level logger."""

    logging.getLogger("discord.voice_state").setLevel(logging.WARNING)
    logging.getLogger("discord.player").setLevel(logging.WARNING)

    logger = logging.getLogger("orca_bot")
    logger.setLevel(LOG_LEVEL)
    logger.propagate = False

    if logger.handlers:
        return logger

    console_handler = logging.StreamHandler()
    console_handler.setLevel(LOG_LEVEL)

    current_date = datetime.date.today().strftime(LOG_DATE_FORMAT)
    log_file = LOG_FILE_TEMPLATE.format(date=current_date)
    file_handler = logging.FileHandler(filename=log_file, mode="a")
    file_handler.setLevel(LOG_LEVEL)

    formatter = logging.Formatter(LOG_FORMAT)
    console_handler.setFormatter(formatter)
    file_handler.setFormatter(formatter)

    logger.addHandler(console_handler)
    logger.addHandler(file_handler)
    return logger


logger = _configure_logger()


def _is_interactive_console() -> bool:
    """Return whether stdin is attached to an interactive terminal."""

    return bool(sys.stdin and sys.stdin.isatty())


def _get_restart_args() -> list[str]:
    """Return the original process arguments needed for a restart."""

    original_args = getattr(sys, "orig_argv", None)
    if original_args:
        return [sys.executable, *original_args[1:]]
    return [sys.executable, *sys.argv]


def _restart_process() -> None:
    """Replace the current process with a fresh copy of the bot."""

    restart_args = _get_restart_args()
    logger.info("Restarting Orca...")
    os.execv(sys.executable, restart_args)


def _build_console_status(profile: str) -> str:
    """Return a readable status summary for the active bot runtime."""

    user_name = client.user.name if client.user else "Not logged in"
    latency_ms = round(client.latency * 1000) if client.is_ready() else "n/a"
    return (
        f"Profile: {profile}\n"
        f"Ready: {client.is_ready()}\n"
        f"Closed: {client.is_closed()}\n"
        f"User: {user_name}\n"
        f"Guilds: {len(client.guilds)}\n"
        f"Voice Clients: {len(client.voice_clients)}\n"
        f"Latency: {latency_ms} ms"
    )


def _console_reader(
    loop: asyncio.AbstractEventLoop,
    command_queue: asyncio.Queue[str],
) -> None:
    """Read console commands from stdin and forward them to the event loop."""

    while True:
        try:
            command = input(CONSOLE_PROMPT)
        except EOFError:
            command = "exit"
        except Exception as exc:
            logger.error("Console input failed: %s", exc)
            break

        try:
            loop.call_soon_threadsafe(command_queue.put_nowait, command)
        except RuntimeError:
            break

        if command.strip().lower() in EXIT_COMMANDS | RESTART_COMMANDS:
            break


async def _handle_console_commands(state: RuntimeCommandState) -> None:
    """Handle runtime console commands while the bot is active."""

    if not _is_interactive_console():
        return

    loop = asyncio.get_running_loop()
    command_queue: asyncio.Queue[str] = asyncio.Queue()
    reader_thread = threading.Thread(
        target=_console_reader,
        args=(loop, command_queue),
        name="orca-console-reader",
        daemon=True,
    )
    reader_thread.start()

    print(CONSOLE_HELP_TEXT)

    while not state.stop_requested and not state.restart_requested:
        raw_command = await command_queue.get()
        command = raw_command.strip().lower()

        if not command:
            continue

        if command in HELP_COMMANDS:
            print(CONSOLE_HELP_TEXT)
            continue

        if command in STATUS_COMMANDS:
            print(_build_console_status(state.profile))
            continue

        if command in EXIT_COMMANDS:
            state.stop_requested = True
            logger.info("Shutdown requested from console.")
            if not client.is_closed():
                await client.close()
            return

        if command in RESTART_COMMANDS:
            state.stop_requested = True
            state.restart_requested = True
            logger.info("Restart requested from console.")
            if not client.is_closed():
                await client.close()
            return

        print(f"Unknown console command: {command}")
        print(CONSOLE_HELP_TEXT)


async def load_extensions() -> None:
    """Load every cog module from the configured cogs directory."""

    loaded_cogs = 0
    failed_cogs: list[str] = []

    for path in sorted(COGS_DIR.glob("*.py")):
        if path.name == COG_INIT_FILE:
            continue

        extension = f"orca_bot.cogs.{path.stem}"
        try:
            await client.load_extension(extension)
            loaded_cogs += 1
        except Exception as exc:
            logger.error("Failed to load extension %s: %s", path.name, exc)
            failed_cogs.append(path.name)

    logger.info("Loaded %s cogs successfully.", loaded_cogs)
    if failed_cogs:
        logger.warning(
            "Failed to load %s cog(s): %s",
            len(failed_cogs),
            ", ".join(failed_cogs),
        )
    else:
        logger.info("All cogs loaded successfully.")


async def main() -> bool:
    """Start the bot runtime and return whether a restart was requested."""

    global _persistent_views_registered
    profile, token = _resolve_runtime_credentials()
    command_state = RuntimeCommandState(profile=profile)
    console_task: asyncio.Task[None] | None = None

    if not _persistent_views_registered:
        client.add_view(NowPlayingButtons())
        _persistent_views_registered = True

    logger.info("Starting Orca with profile '%s'.", profile)
    console_task = asyncio.create_task(_handle_console_commands(command_state))

    try:
        for attempt in range(STARTUP_RETRY_ATTEMPTS):
            try:
                await load_extensions()
                await client.start(token)
                break
            except Exception as exc:
                logger.error("Failed to start bot: %s", exc)
                if command_state.stop_requested:
                    break
                if attempt == 0:
                    logger.info("Retrying...")
                else:
                    logger.error(
                        "Failed to load again. Check the server and restart."
                    )
                    break
    finally:
        if console_task is not None:
            console_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await console_task

    return command_state.restart_requested


def run() -> None:
    """Run the bot inside a managed asyncio event loop."""

    should_restart = asyncio.run(main())
    if should_restart:
        _restart_process()


if __name__ == "__main__":
    run()
