"""Ping command cog for checking Orca latency."""

import logging

from discord.ext import commands

PING_COMMAND_NAME = "ping"
PING_COMMAND_DESCRIPTION = "Checks your latency to Orca's server."
MILLISECONDS_PER_SECOND = 1000

log = logging.getLogger(__name__)


class Ping(commands.Cog):
    """Ping command for reporting the bot latency."""

    def __init__(self, bot: commands.Bot) -> None:
        """Store the bot instance for command access."""

        self.bot = bot

    @commands.hybrid_command(
        name=PING_COMMAND_NAME,
        description=PING_COMMAND_DESCRIPTION,
    )
    async def ping(self, ctx: commands.Context) -> None:
        """Send the current bot latency to the invoking context."""

        assert ctx.guild is not None

        latency_ms = round(self.bot.latency * MILLISECONDS_PER_SECOND)

        log.info(
            '%s used the ping command in server "%s" (%s)',
            ctx.author,
            ctx.guild.name,
            ctx.guild.id,
        )
        await ctx.send(f"{latency_ms}ms")


async def setup(bot: commands.Bot) -> None:
    """Register the ping cog with the bot."""

    await bot.add_cog(Ping(bot))
