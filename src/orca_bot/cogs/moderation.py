"""Moderation commands for Orca."""

import logging
from datetime import timedelta
from typing import Literal

import discord
from discord.ext import commands

PURGE_AMOUNTS = Literal["10", "25", "50", "100", "All"]
DM_FAILED_NOTICE = " (could not send DM — user may have DMs disabled)"

log = logging.getLogger(__name__)


def _success_embed(description: str) -> discord.Embed:
    return discord.Embed(description=f"✅ {description}", color=discord.Color.green())


def _error_embed(description: str) -> discord.Embed:
    return discord.Embed(description=f"❌ {description}", color=discord.Color.red())


def _dm_embed(title: str, description: str) -> discord.Embed:
    return discord.Embed(
        title=title, description=description, color=discord.Color.blue()
    )


async def _try_dm(user: discord.Member, embed: discord.Embed) -> bool:
    """Attempt to DM a user. Returns True if successful."""
    try:
        await user.send(embed=embed)
        return True
    except (discord.Forbidden, discord.HTTPException):
        return False


def _hierarchy_check(
    actor: discord.Member,
    bot: discord.Member,
    target: discord.Member,
) -> str | None:
    """Return an error message if the action is not permitted, else None.

    Uses strict ordering: actor rank must be strictly greater than target rank.
    Equal ranks cancel each other out and block the action.
    Server owner bypasses actor rank check but bot rank is always enforced.
    """
    if target == actor.guild.owner:
        return "You cannot action the server owner."
    if actor != actor.guild.owner and target.top_role >= actor.top_role:
        return "You cannot action someone with an equal or higher role than yours."
    if target.top_role >= bot.top_role:
        return "My highest role must be above the target's role to perform this action."
    return None


def _log_action(
    ctx: commands.Context,
    action: str,
    target: str,
    reason: str | None,
) -> None:
    assert ctx.guild is not None
    log.info(
        '%s — %s actioned %s in "%s" (%s). Reason: %s',
        action,
        ctx.author,
        target,
        ctx.guild.name,
        ctx.guild.id,
        reason or "None",
    )


class PurgeConfirmation(discord.ui.View):
    """Confirmation dialog for the purge command."""

    def __init__(
        self,
        ctx: commands.Context,
        amount: str,
        user: discord.Member | None,
    ) -> None:
        super().__init__(timeout=30)
        self.ctx = ctx
        self.amount = amount
        self.target_user = user
        self.message: discord.Message | None = None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user != self.ctx.author:
            await interaction.response.send_message(
                embed=_error_embed("Only the command author can use these buttons."),
                ephemeral=True,
            )
            return False
        return True

    @discord.ui.button(label="Confirm", style=discord.ButtonStyle.danger)
    async def confirm(
        self,
        interaction: discord.Interaction,
        _button: discord.ui.Button,
    ) -> None:
        await interaction.response.defer()
        limit = None if self.amount == "All" else int(self.amount)

        def check(m: discord.Message) -> bool:
            return self.target_user is None or m.author == self.target_user

        try:
            deleted = await interaction.channel.purge(limit=limit, check=check)
        except discord.Forbidden:
            if self.message:
                try:
                    await self.message.edit(
                        embed=_error_embed(
                            "I don't have permission to delete messages in this channel."
                        ),
                        view=None,
                    )
                except (discord.HTTPException, discord.Forbidden):
                    pass
            return

        assert self.ctx.guild is not None
        _log_action(
            self.ctx,
            "Purge",
            f"{len(deleted)} messages"
            + (f" from {self.target_user}" if self.target_user else ""),
            None,
        )

        if self.message:
            try:
                await self.message.edit(
                    embed=_success_embed(
                        f"Deleted **{len(deleted)}** message(s)"
                        + (
                            f" from {self.target_user.mention}"
                            if self.target_user
                            else ""
                        )
                        + "."
                    ),
                    view=None,
                )
            except (discord.HTTPException, discord.Forbidden):
                pass

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(
        self,
        interaction: discord.Interaction,
        _button: discord.ui.Button,
    ) -> None:
        await interaction.response.defer()
        if self.message:
            try:
                await self.message.edit(
                    embed=discord.Embed(
                        description="Purge cancelled.", color=discord.Color.greyple()
                    ),
                    view=None,
                )
            except (discord.HTTPException, discord.Forbidden):
                pass

    async def on_timeout(self) -> None:
        if self.message:
            try:
                await self.message.edit(
                    embed=discord.Embed(
                        description="Purge confirmation timed out.",
                        color=discord.Color.greyple(),
                    ),
                    view=None,
                )
            except (discord.HTTPException, discord.Forbidden):
                pass


class Moderation(commands.Cog):
    """Moderation commands for server management."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @commands.hybrid_command(name="kick", description="Kick a member from the server.")
    @commands.has_permissions(kick_members=True)
    @commands.guild_only()
    async def kick(
        self,
        ctx: commands.Context,
        user: discord.Member,
        *,
        reason: str | None = None,
    ) -> None:
        """Kick a member from the guild."""

        await ctx.defer(ephemeral=True)

        if user == ctx.author:
            await ctx.send(
                embed=_error_embed("You cannot kick yourself."), ephemeral=True
            )
            return

        if err := _hierarchy_check(ctx.author, ctx.guild.me, user):
            await ctx.send(embed=_error_embed(err), ephemeral=True)
            return

        dm_sent = await _try_dm(
            user,
            _dm_embed(
                f"You have been kicked from {ctx.guild.name}",
                f"**Reason:** {reason or 'No reason provided.'}",
            ),
        )

        try:
            await user.kick(reason=reason)
        except discord.Forbidden:
            await ctx.send(
                embed=_error_embed("I don't have permission to kick that user."),
                ephemeral=True,
            )
            return

        _log_action(ctx, "Kick", str(user), reason)
        notice = "" if dm_sent else DM_FAILED_NOTICE
        await ctx.send(
            embed=_success_embed(
                f"{user.mention} has been kicked.{notice}"
                + (f"\n**Reason:** {reason}" if reason else "")
            ),
            ephemeral=True,
        )

    @commands.hybrid_command(name="ban", description="Ban a member from the server.")
    @commands.has_permissions(ban_members=True)
    @commands.guild_only()
    async def ban(
        self,
        ctx: commands.Context,
        user: discord.Member,
        delete_days: int = 0,
        *,
        reason: str | None = None,
    ) -> None:
        """Ban a member from the guild."""

        await ctx.defer(ephemeral=True)

        if user == ctx.author:
            await ctx.send(
                embed=_error_embed("You cannot ban yourself."), ephemeral=True
            )
            return

        if err := _hierarchy_check(ctx.author, ctx.guild.me, user):
            await ctx.send(embed=_error_embed(err), ephemeral=True)
            return

        if not 0 <= delete_days <= 7:
            await ctx.send(
                embed=_error_embed("delete_days must be between 0 and 7."),
                ephemeral=True,
            )
            return

        dm_sent = await _try_dm(
            user,
            _dm_embed(
                f"You have been banned from {ctx.guild.name}",
                f"**Reason:** {reason or 'No reason provided.'}",
            ),
        )

        try:
            await user.ban(
                reason=reason,
                delete_message_days=delete_days,
            )
        except discord.Forbidden:
            await ctx.send(
                embed=_error_embed("I don't have permission to ban that user."),
                ephemeral=True,
            )
            return

        _log_action(ctx, "Ban", str(user), reason)
        notice = "" if dm_sent else DM_FAILED_NOTICE
        await ctx.send(
            embed=_success_embed(
                f"{user.mention} has been banned.{notice}"
                + (f"\n**Reason:** {reason}" if reason else "")
            ),
            ephemeral=True,
        )

    @commands.hybrid_command(name="unban", description="Unban a user by their ID.")
    @commands.has_permissions(ban_members=True)
    @commands.guild_only()
    async def unban(
        self,
        ctx: commands.Context,
        user_id: str,
        *,
        reason: str | None = None,
    ) -> None:
        """Unban a previously banned user by Discord user ID."""

        await ctx.defer(ephemeral=True)

        try:
            user_id_int = int(user_id)
        except ValueError:
            await ctx.send(
                embed=_error_embed(
                    "Invalid user ID. Please provide a numeric Discord user ID."
                ),
                ephemeral=True,
            )
            return

        try:
            ban_entry = await ctx.guild.fetch_ban(discord.Object(id=user_id_int))
        except discord.NotFound:
            await ctx.send(
                embed=_error_embed(f"No ban found for user ID `{user_id}`."),
                ephemeral=True,
            )
            return
        except discord.HTTPException:
            await ctx.send(
                embed=_error_embed(
                    "Failed to fetch ban information. Please try again."
                ),
                ephemeral=True,
            )
            return

        try:
            await ctx.guild.unban(ban_entry.user, reason=reason)
        except discord.Forbidden:
            await ctx.send(
                embed=_error_embed("I don't have permission to unban that user."),
                ephemeral=True,
            )
            return

        _log_action(ctx, "Unban", str(ban_entry.user), reason)
        await ctx.send(
            embed=_success_embed(
                f"**{ban_entry.user}** has been unbanned."
                + (f"\n**Reason:** {reason}" if reason else "")
            ),
            ephemeral=True,
        )

    @commands.hybrid_command(
        name="timeout",
        description="Timeout a member for a specified number of minutes.",
    )
    @commands.has_permissions(moderate_members=True)
    @commands.guild_only()
    async def timeout(
        self,
        ctx: commands.Context,
        user: discord.Member,
        minutes: int,
        *,
        reason: str | None = None,
    ) -> None:
        """Apply a timeout to a guild member."""

        await ctx.defer(ephemeral=True)

        if minutes < 1 or minutes > 40320:
            await ctx.send(
                embed=_error_embed(
                    "Duration must be between 1 and 40320 minutes (28 days)."
                ),
                ephemeral=True,
            )
            return

        if err := _hierarchy_check(ctx.author, ctx.guild.me, user):
            await ctx.send(embed=_error_embed(err), ephemeral=True)
            return

        dm_sent = await _try_dm(
            user,
            _dm_embed(
                f"You have been timed out in {ctx.guild.name}",
                f"**Duration:** {minutes} minute(s)\n**Reason:** {reason or 'No reason provided.'}",
            ),
        )

        try:
            await user.timeout(timedelta(minutes=minutes), reason=reason)
        except discord.Forbidden:
            await ctx.send(
                embed=_error_embed("I don't have permission to timeout that user."),
                ephemeral=True,
            )
            return

        _log_action(ctx, f"Timeout ({minutes}m)", str(user), reason)
        notice = "" if dm_sent else DM_FAILED_NOTICE
        await ctx.send(
            embed=_success_embed(
                f"{user.mention} has been timed out for **{minutes}** minute(s).{notice}"
                + (f"\n**Reason:** {reason}" if reason else "")
            ),
            ephemeral=True,
        )

    @commands.hybrid_command(
        name="untimeout", description="Remove a timeout from a member."
    )
    @commands.has_permissions(moderate_members=True)
    @commands.guild_only()
    async def untimeout(
        self,
        ctx: commands.Context,
        user: discord.Member,
        *,
        reason: str | None = None,
    ) -> None:
        """Remove an active timeout from a guild member."""

        await ctx.defer(ephemeral=True)

        if err := _hierarchy_check(ctx.author, ctx.guild.me, user):
            await ctx.send(embed=_error_embed(err), ephemeral=True)
            return

        if not user.is_timed_out():
            await ctx.send(
                embed=_error_embed(f"{user.mention} is not currently timed out."),
                ephemeral=True,
            )
            return

        try:
            await user.timeout(None, reason=reason)
        except discord.Forbidden:
            await ctx.send(
                embed=_error_embed("I don't have permission to remove that timeout."),
                ephemeral=True,
            )
            return

        await _try_dm(
            user,
            _dm_embed(
                f"Your timeout in {ctx.guild.name} has been removed.",
                f"**Reason:** {reason or 'No reason provided.'}",
            ),
        )

        _log_action(ctx, "Untimeout", str(user), reason)
        await ctx.send(
            embed=_success_embed(
                f"{user.mention}'s timeout has been removed."
                + (f"\n**Reason:** {reason}" if reason else "")
            ),
            ephemeral=True,
        )

    @commands.hybrid_command(
        name="purge", description="Bulk delete messages in this channel."
    )
    @commands.has_permissions(manage_messages=True)
    @commands.guild_only()
    async def purge(
        self,
        ctx: commands.Context,
        amount: PURGE_AMOUNTS,
        user: discord.Member | None = None,
    ) -> None:
        """Prompt for confirmation and bulk delete messages."""

        await ctx.defer(ephemeral=True)

        if amount == "All":
            target_str = f" from {user.mention}" if user else ""
            description = (
                f"⚠️ This will delete **ALL** recent messages{target_str} in this channel."
                "\n\nMessages older than 14 days cannot be bulk deleted by Discord."
                "\n\n**This cannot be undone.**"
            )
        else:
            target_str = f" from {user.mention}" if user else ""
            description = (
                f"Are you sure you want to delete the last **{amount}** message(s){target_str}?"
                "\n\n**This cannot be undone.**"
            )

        view = PurgeConfirmation(ctx, amount, user)
        view.message = await ctx.send(
            embed=discord.Embed(
                description=description,
                color=discord.Color.orange(),
            ),
            view=view,
            ephemeral=True,
        )

    @commands.hybrid_command(
        name="changerole",
        description="Add or remove a role from a member (toggles).",
    )
    @commands.has_permissions(manage_roles=True)
    @commands.guild_only()
    async def changerole(
        self,
        ctx: commands.Context,
        user: discord.Member,
        role: discord.Role,
    ) -> None:
        """Toggle a role on a guild member — adds if not present, removes if present."""

        await ctx.defer(ephemeral=True)

        if role >= ctx.guild.me.top_role:
            await ctx.send(
                embed=_error_embed(
                    "I cannot assign or remove a role equal to or above my own."
                ),
                ephemeral=True,
            )
            return

        if role >= ctx.author.top_role:
            await ctx.send(
                embed=_error_embed(
                    "You cannot assign or remove a role equal to or above your own."
                ),
                ephemeral=True,
            )
            return

        try:
            if role in user.roles:
                await user.remove_roles(role, reason=f"Role toggled by {ctx.author}")
                action = "removed from"
            else:
                await user.add_roles(role, reason=f"Role toggled by {ctx.author}")
                action = "added to"
        except discord.Forbidden:
            await ctx.send(
                embed=_error_embed("I don't have permission to modify that role."),
                ephemeral=True,
            )
            return

        _log_action(ctx, f"Role {action} {user}", str(role), None)
        await ctx.send(
            embed=_success_embed(
                f"{role.mention} has been **{action}** {user.mention}."
            ),
            ephemeral=True,
        )

    @kick.error
    @ban.error
    @unban.error
    @timeout.error
    @untimeout.error
    @purge.error
    @changerole.error
    async def moderation_error(
        self, ctx: commands.Context, error: commands.CommandError
    ) -> None:
        """Handle permission and other errors for all moderation commands."""

        if isinstance(error, commands.MissingPermissions):
            await ctx.send(
                embed=_error_embed("You don't have permission to use this command."),
                ephemeral=True,
            )
        elif isinstance(error, commands.BotMissingPermissions):
            await ctx.send(
                embed=_error_embed("I don't have the required permissions to do that."),
                ephemeral=True,
            )
        else:
            await ctx.send(
                embed=_error_embed(f"An error occurred: {error}"),
                ephemeral=True,
            )


async def setup(bot: commands.Bot) -> None:
    """Register the moderation cog with the bot."""

    await bot.add_cog(Moderation(bot))
