"""Utility commands for Orca."""

import random
import re
from datetime import timezone

import discord
from discord.ext import commands

EIGHT_BALL_POSITIVE = (
    "It is certain.",
    "It is decidedly so.",
    "Without a doubt.",
    "Yes, definitely.",
    "You may rely on it.",
    "As I see it, yes.",
    "Most likely.",
    "Outlook good.",
    "Yes.",
    "Signs point to yes.",
)
EIGHT_BALL_NEUTRAL = (
    "Reply hazy, try again.",
    "Ask again later.",
    "Better not tell you now.",
    "Cannot predict now.",
    "Concentrate and ask again.",
)
EIGHT_BALL_NEGATIVE = (
    "Don't count on it.",
    "My reply is no.",
    "My sources say no.",
    "Outlook not so good.",
    "Very doubtful.",
)

COINFLIP_OUTCOMES = ("Heads", "Tails")
COINFLIP_COLOUR = discord.Color.gold()
USERINFO_COLOUR = discord.Color.blue()
SERVERINFO_COLOUR = discord.Color.blue()
AVATAR_COLOUR = discord.Color.blue()
CHOOSE_COLOUR = discord.Color.purple()
ROLL_COLOUR = discord.Color.orange()
ROLEINFO_COLOUR = discord.Color.blue()
ROLL_PATTERN = re.compile(r"^(\d+)d(\d+)$", re.IGNORECASE)
ROLL_MAX_DICE = 100
ROLL_MAX_SIDES = 10000


def _eight_ball_colour(response: str) -> discord.Color:
    if response in EIGHT_BALL_POSITIVE:
        return discord.Color.green()
    if response in EIGHT_BALL_NEUTRAL:
        return discord.Color.greyple()
    return discord.Color.red()


def _format_timestamp(dt) -> str:
    if dt is None:
        return "Unknown"
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return f"<t:{int(dt.timestamp())}:F>"


class Utility(commands.Cog):
    """General utility commands."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @commands.hybrid_command(name="userinfo", description="Show info about a user.")
    async def userinfo(
        self,
        ctx: commands.Context,
        user: discord.Member | None = None,
    ) -> None:
        """Display profile information for a server member."""

        await ctx.defer()
        member = user or ctx.author

        roles = [r.mention for r in reversed(member.roles) if r.name != "@everyone"]
        roles_display = ", ".join(roles) if roles else "None"

        embed = discord.Embed(
            title=f"👤 {member}",
            color=USERINFO_COLOUR,
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.add_field(name="Display Name", value=member.display_name, inline=True)
        embed.add_field(name="User ID", value=str(member.id), inline=True)
        embed.add_field(name="Bot", value="Yes" if member.bot else "No", inline=True)
        embed.add_field(
            name="Account Created",
            value=_format_timestamp(member.created_at),
            inline=False,
        )
        embed.add_field(
            name="Joined Server",
            value=_format_timestamp(member.joined_at),
            inline=False,
        )
        embed.add_field(
            name=f"Roles ({len(roles)})",
            value=roles_display[:1024],
            inline=False,
        )
        await ctx.send(embed=embed)

    @commands.hybrid_command(
        name="serverinfo", description="Show info about the server."
    )
    @commands.guild_only()
    async def serverinfo(self, ctx: commands.Context) -> None:
        """Display information about the current guild."""

        await ctx.defer()
        guild = ctx.guild

        owner = guild.owner
        embed = discord.Embed(
            title=f"🏠 {guild.name}",
            color=SERVERINFO_COLOUR,
        )
        if guild.icon:
            embed.set_thumbnail(url=guild.icon.url)
        embed.add_field(name="Server ID", value=str(guild.id), inline=True)
        embed.add_field(
            name="Owner", value=owner.mention if owner else "Unknown", inline=True
        )
        embed.add_field(name="Boost Level", value=str(guild.premium_tier), inline=True)
        embed.add_field(name="Members", value=str(guild.member_count), inline=True)
        embed.add_field(name="Channels", value=str(len(guild.channels)), inline=True)
        embed.add_field(name="Roles", value=str(len(guild.roles)), inline=True)
        embed.add_field(
            name="Created",
            value=_format_timestamp(guild.created_at),
            inline=False,
        )
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="avatar", description="Show a user's avatar.")
    async def avatar(
        self,
        ctx: commands.Context,
        user: discord.Member | None = None,
    ) -> None:
        """Display the full-size avatar for a server member."""

        await ctx.defer()
        member = user or ctx.author

        embed = discord.Embed(
            title=f"{member.display_name}'s Avatar",
            color=AVATAR_COLOUR,
        )
        embed.set_image(url=member.display_avatar.url)
        await ctx.send(embed=embed)

    @commands.hybrid_command(
        name="8ball", description="Ask the magic 8 ball a question."
    )
    async def eight_ball(self, ctx: commands.Context, *, question: str) -> None:
        """Return a magic 8 ball response for the given question."""

        all_responses = EIGHT_BALL_POSITIVE + EIGHT_BALL_NEUTRAL + EIGHT_BALL_NEGATIVE
        response = random.choice(all_responses)

        embed = discord.Embed(
            title="🎱 Magic 8 Ball",
            color=_eight_ball_colour(response),
        )
        embed.add_field(name="Question", value=question, inline=False)
        embed.add_field(name="Answer", value=response, inline=False)
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="coinflip", description="Flip a coin.")
    async def coinflip(self, ctx: commands.Context) -> None:
        """Flip a coin and return heads or tails."""

        result = random.choice(COINFLIP_OUTCOMES)
        embed = discord.Embed(
            title="🪙 Coin Flip",
            description=f"**{result}**",
            color=COINFLIP_COLOUR,
        )
        await ctx.send(embed=embed)

    @commands.hybrid_command(
        name="choose",
        description="Choose randomly from up to five options.",
    )
    async def choose(
        self,
        ctx: commands.Context,
        option1: str,
        option2: str,
        option3: str | None = None,
        option4: str | None = None,
        option5: str | None = None,
    ) -> None:
        """Pick one option at random from the provided choices."""

        choices = [
            o for o in [option1, option2, option3, option4, option5] if o is not None
        ]
        result = random.choice(choices)
        embed = discord.Embed(title="🎲 Choose", color=CHOOSE_COLOUR)
        embed.add_field(
            name="Options", value="\n".join(f"• {c}" for c in choices), inline=False
        )
        embed.add_field(name="Chosen", value=f"**{result}**", inline=False)
        await ctx.send(embed=embed)

    @commands.hybrid_command(
        name="roll",
        description="Roll dice using NdN notation (e.g. 2d6). Defaults to 1d6.",
    )
    async def roll(self, ctx: commands.Context, dice: str = "1d6") -> None:
        """Roll one or more dice and display individual results and total."""

        match = ROLL_PATTERN.match(dice.strip())
        if not match:
            await ctx.send(
                embed=discord.Embed(
                    description="Invalid format. Use NdN notation, e.g. `2d6` or `1d20`.",
                    color=discord.Color.red(),
                )
            )
            return

        count, sides = int(match.group(1)), int(match.group(2))

        if count < 1 or count > ROLL_MAX_DICE:
            await ctx.send(
                embed=discord.Embed(
                    description=f"Number of dice must be between 1 and {ROLL_MAX_DICE}.",
                    color=discord.Color.red(),
                )
            )
            return

        if sides < 2 or sides > ROLL_MAX_SIDES:
            await ctx.send(
                embed=discord.Embed(
                    description=f"Number of sides must be between 2 and {ROLL_MAX_SIDES}.",
                    color=discord.Color.red(),
                )
            )
            return

        rolls = [random.randint(1, sides) for _ in range(count)]
        total = sum(rolls)

        embed = discord.Embed(
            title=f"🎲 Roll {dice}",
            color=ROLL_COLOUR,
        )
        if count > 1:
            embed.add_field(
                name="Rolls",
                value=" + ".join(str(r) for r in rolls),
                inline=False,
            )
        embed.add_field(name="Total", value=f"**{total}**", inline=False)
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="roleinfo", description="Show info about a role.")
    @commands.guild_only()
    async def roleinfo(self, ctx: commands.Context, role: discord.Role) -> None:
        """Display information about a guild role."""

        await ctx.defer()

        colour_hex = str(role.colour) if role.colour.value else "Default"
        members = len(role.members)

        embed = discord.Embed(
            title=f"🎭 {role.name}",
            color=role.colour if role.colour.value else ROLEINFO_COLOUR,
        )
        embed.add_field(name="Role ID", value=str(role.id), inline=True)
        embed.add_field(name="Colour", value=colour_hex, inline=True)
        embed.add_field(name="Members", value=str(members), inline=True)
        embed.add_field(
            name="Hoisted", value="Yes" if role.hoist else "No", inline=True
        )
        embed.add_field(
            name="Mentionable", value="Yes" if role.mentionable else "No", inline=True
        )
        embed.add_field(
            name="Managed", value="Yes" if role.managed else "No", inline=True
        )
        embed.add_field(
            name="Created",
            value=_format_timestamp(role.created_at),
            inline=False,
        )
        await ctx.send(embed=embed)


async def setup(bot: commands.Bot) -> None:
    """Register the utility cog with the bot."""

    await bot.add_cog(Utility(bot))
