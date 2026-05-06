"""Moderation command cog for Orca."""

import logging

import discord
from discord.ext import commands

KICK_COMMAND_NAME = "kick"
KICK_COMMAND_DESCRIPTION = (
    "Kick a member from your server. You must have permissions to use "
    "this command."
)
KICK_COMMAND_OPTIONS = [
    {
        "name": "user",
        "description": "User to kick from the server.",
        "type": 6,
        "required": True,
    }
]
KICK_REASON = "Kicked by moderator."
KICK_PERMISSION_MESSAGE = "You do not have permission to kick members."
KICK_SUCCESS_MESSAGE = "{mention} has been kicked from the server."
KICK_FORBIDDEN_MESSAGE = (
    "I'm sorry, I couldn't kick that user. Make sure my role is higher "
    "than the user you want to kick."
)
CHANGE_ROLE_COMMAND_NAME = "changerole"
CHANGE_ROLE_COMMAND_DESCRIPTION = (
    "Change the role of a specified user. You must have permissions to "
    "use this command."
)
CHANGE_ROLE_COMMAND_OPTIONS = [
    {
        "name": "user",
        "description": "Type a user and the role to give them.",
        "type": 6,
        "required": True,
    }
]
CHANGE_ROLE_PERMISSION_MESSAGE = "You do not have permission to modify roles."
BOT_ROLE_PERMISSION_MESSAGE = "I do not have permission to modify roles."
CHANGE_ROLE_SUCCESS_MESSAGE = (
    "{display_name}'s role has been changed to {role}."
)
CHANGE_ROLE_FORBIDDEN_MESSAGE = (
    "I'm sorry, I couldn't change that user's role due to insufficient "
    "permissions."
)

log = logging.getLogger(__name__)


def _format_member_tag(member: discord.Member) -> str:
    """Return a readable member tag for moderation logging."""

    return member.display_name


def _log_guild_action(ctx: commands.Context, action: str) -> None:
    """Write a moderation log entry for the current guild context."""

    assert ctx.guild is not None

    log.info(
        '%s in server "%s" (%s)',
        action,
        ctx.guild.name,
        ctx.guild.id,
    )


class Moderation(commands.Cog):
    """Moderation commands for kicking members and changing roles."""

    def __init__(self, bot: commands.Bot) -> None:
        """Store the bot instance for moderation commands."""

        self.bot = bot

    @commands.hybrid_command(
        name=KICK_COMMAND_NAME,
        description=KICK_COMMAND_DESCRIPTION,
        options=KICK_COMMAND_OPTIONS,
    )
    async def kick(
        self,
        ctx: commands.Context,
        user: discord.Member,
    ) -> None:
        """Kick a member from the guild if the caller has permission."""

        actor_tag = _format_member_tag(ctx.author)
        target_tag = _format_member_tag(user)

        if not ctx.author.guild_permissions.kick_members:
            _log_guild_action(
                ctx,
                f"{actor_tag} tried to kick {target_tag}, but does not have "
                "permission to do so",
            )
            await ctx.send(KICK_PERMISSION_MESSAGE)
            return

        try:
            await user.kick(reason=KICK_REASON)
            _log_guild_action(ctx, f"{actor_tag} kicked {target_tag}")
            await ctx.send(KICK_SUCCESS_MESSAGE.format(mention=user.mention))
        except discord.Forbidden:
            await ctx.send(KICK_FORBIDDEN_MESSAGE)

    @commands.hybrid_command(
        name=CHANGE_ROLE_COMMAND_NAME,
        description=CHANGE_ROLE_COMMAND_DESCRIPTION,
        options=CHANGE_ROLE_COMMAND_OPTIONS,
    )
    async def changerole(
        self,
        ctx: commands.Context,
        user: discord.Member,
        role: discord.Role,
    ) -> None:
        """Add the requested role to a member if permissions allow it."""

        actor_tag = _format_member_tag(ctx.author)
        target_tag = _format_member_tag(user)

        if not ctx.author.guild_permissions.manage_roles:
            await ctx.send(CHANGE_ROLE_PERMISSION_MESSAGE)
            _log_guild_action(
                ctx,
                f"{actor_tag} tried to change {target_tag}'s role to "
                f"({role.name}), but does not have permission to do so.",
            )
            return

        assert ctx.guild is not None

        guild_member = ctx.guild.me
        if (
            guild_member is None
            or not guild_member.guild_permissions.manage_roles
        ):
            await ctx.send(BOT_ROLE_PERMISSION_MESSAGE)
            return

        try:
            await user.add_roles(role)
            await ctx.send(
                CHANGE_ROLE_SUCCESS_MESSAGE.format(
                    display_name=user.display_name,
                    role=role.name,
                )
            )
            _log_guild_action(
                ctx,
                f"{actor_tag} changed {target_tag}'s role to ({role.name}).",
            )
        except discord.Forbidden:
            await ctx.send(CHANGE_ROLE_FORBIDDEN_MESSAGE)


async def setup(bot: commands.Bot) -> None:
    """Register the moderation cog with the bot."""

    await bot.add_cog(Moderation(bot))
