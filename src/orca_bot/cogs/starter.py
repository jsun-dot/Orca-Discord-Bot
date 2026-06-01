"""Startup and presence management cog for Orca."""

import unicodedata
from datetime import datetime, timezone

import discord
import pytz
from discord.ext import commands

EASTERN_TIMEZONE_NAME = "US/Eastern"
EASTERN_TIME_FORMAT = "%Y-%m-%d %H:%M:%S"
PRESENCE_ACTIVITY_NAME = "till I can't swim."
ONLINE_BANNER_TITLE = "🤖  BOT IS NOW ONLINE! 🤖"
ONLINE_BANNER_TIME_LABEL = "Time (US/Eastern): {time}"
OUTER_BANNER_WIDTH = 66
INNER_BANNER_WIDTH = 54
INNER_BANNER_LEFT_PADDING = 6
INNER_BANNER_RIGHT_PADDING = 4
LOGIN_SUMMARY_HEADER = "📋 Logged in as:"
LOGIN_SUMMARY_SEPARATOR_WIDTH = 60


def _get_eastern_time_string() -> str:
    """Return the current time formatted in the US/Eastern timezone."""

    eastern_timezone = pytz.timezone(EASTERN_TIMEZONE_NAME)
    eastern_now = datetime.now(timezone.utc).astimezone(eastern_timezone)
    return eastern_now.strftime(EASTERN_TIME_FORMAT)


def _build_banner_border(left: str, fill: str, right: str, width: int) -> str:
    """Return a banner border line with the given width."""

    return f"{left}{fill * width}{right}"


def _visual_len(text: str) -> int:
    """Return the visual display width, counting wide characters (e.g. emoji) as 2."""

    width = 0
    for char in text:
        eaw = unicodedata.east_asian_width(char)
        width += 2 if eaw in ("W", "F") else 1
    return width


def _build_centered_banner_line(content: str = "") -> str:
    """Return a centered line inside the outer banner frame."""

    extra = _visual_len(content) - len(content)
    return f"║{content.center(OUTER_BANNER_WIDTH - extra)}║"


def _build_inner_banner_line(left: str, content: str, right: str) -> str:
    """Return a formatted inner box line for the startup banner."""

    padded_content = content.ljust(INNER_BANNER_WIDTH)
    return (
        f"║{' ' * INNER_BANNER_LEFT_PADDING}"
        f"{left}{padded_content}{right}"
        f"{' ' * INNER_BANNER_RIGHT_PADDING}║"
    )


def _build_login_summary(username: str, user_id: int) -> str:
    """Return the formatted login summary for the current bot user."""

    separator = "─" * LOGIN_SUMMARY_SEPARATOR_WIDTH
    return "\n".join(
        (
            separator,
            LOGIN_SUMMARY_HEADER,
            f"Username: {username}",
            f"User ID : {user_id}",
            separator,
        )
    )


class Starter(commands.Cog):
    """Cog responsible for bot startup tasks and presence updates."""

    def __init__(self, client: commands.Bot) -> None:
        """Store the bot client used by the cog."""

        self.client = client

    def _build_online_banner(self) -> str:
        """Return the formatted startup banner."""

        return "\n".join(
            (
                _build_banner_border("╔", "═", "╗", OUTER_BANNER_WIDTH),
                _build_centered_banner_line(),
                _build_centered_banner_line(ONLINE_BANNER_TITLE),
                _build_centered_banner_line(),
                _build_inner_banner_line(
                    "╭",
                    "─" * INNER_BANNER_WIDTH,
                    "╮",
                ),
                _build_inner_banner_line(
                    "│",
                    "  "
                    + ONLINE_BANNER_TIME_LABEL.format(time=_get_eastern_time_string()),
                    "│",
                ),
                _build_inner_banner_line(
                    "╰",
                    "─" * INNER_BANNER_WIDTH,
                    "╯",
                ),
                _build_centered_banner_line(),
                _build_banner_border("╚", "═", "╝", OUTER_BANNER_WIDTH),
            )
        )

    def _build_login_summary(self) -> str:
        """Return the formatted login summary for the current bot user."""

        assert self.client.user is not None

        return _build_login_summary(
            username=self.client.user.name,
            user_id=self.client.user.id,
        )

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        """Sync commands, log startup details, and update the bot presence."""

        await self.client.tree.sync()

        if self.client.user is not None:
            print(f"\n{self._build_online_banner()}")
            print(self._build_login_summary())
            print(getattr(self.client, "console_help_text", ""))

        await self.client.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.playing,
                name=PRESENCE_ACTIVITY_NAME,
            )
        )


async def setup(client: commands.Bot) -> None:
    """Register the starter cog with the bot."""

    await client.add_cog(Starter(client))
