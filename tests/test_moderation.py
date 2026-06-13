from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock

ROOT = Path(__file__).resolve().parent.parent
root_str = str(ROOT)
if root_str not in sys.path:
    sys.path.insert(0, root_str)

import discord
from orca_bot.cogs.moderation import (
    _error_embed,
    _hierarchy_check,
    _success_embed,
)


class FakeRole:
    """Minimal role stub that supports position-based comparison."""

    def __init__(self, position: int) -> None:
        self.position = position

    def __ge__(self, other: FakeRole) -> bool:
        return self.position >= other.position

    def __gt__(self, other: FakeRole) -> bool:
        return self.position > other.position

    def __lt__(self, other: FakeRole) -> bool:
        return self.position < other.position

    def __le__(self, other: FakeRole) -> bool:
        return self.position <= other.position

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, FakeRole):
            return NotImplemented
        return self.position == other.position


def _make_member(position: int, is_owner: bool = False) -> MagicMock:
    """Create a mock member with a given top role position."""
    guild = MagicMock()
    member = MagicMock()
    member.top_role = FakeRole(position)
    member.guild = guild
    if is_owner:
        guild.owner = member
    else:
        guild.owner = MagicMock()
    return member


class HierarchyCheckTests(unittest.TestCase):
    def test_target_is_guild_owner_always_blocked(self) -> None:
        owner = _make_member(position=10, is_owner=True)
        actor = _make_member(position=5)
        actor.guild = owner.guild
        bot = _make_member(position=8)
        bot.guild = owner.guild

        result = _hierarchy_check(actor, bot, owner.guild.owner)
        self.assertIsNotNone(result)
        self.assertIn("owner", result.lower())

    def test_actor_rank_strictly_greater_than_target_allowed(self) -> None:
        guild = MagicMock()
        actor = _make_member(position=5)
        actor.guild = guild
        target = _make_member(position=3)
        target.guild = guild
        bot = _make_member(position=8)
        bot.guild = guild
        guild.owner = MagicMock()

        self.assertIsNone(_hierarchy_check(actor, bot, target))

    def test_equal_ranks_cancel_out_and_block(self) -> None:
        guild = MagicMock()
        actor = _make_member(position=5)
        actor.guild = guild
        target = _make_member(position=5)
        target.guild = guild
        bot = _make_member(position=8)
        bot.guild = guild
        guild.owner = MagicMock()

        result = _hierarchy_check(actor, bot, target)
        self.assertIsNotNone(result)

    def test_actor_rank_lower_than_target_blocked(self) -> None:
        guild = MagicMock()
        actor = _make_member(position=3)
        actor.guild = guild
        target = _make_member(position=5)
        target.guild = guild
        bot = _make_member(position=8)
        bot.guild = guild
        guild.owner = MagicMock()

        result = _hierarchy_check(actor, bot, target)
        self.assertIsNotNone(result)

    def test_bot_rank_too_low_blocked_even_if_actor_rank_sufficient(self) -> None:
        guild = MagicMock()
        actor = _make_member(position=5)
        actor.guild = guild
        target = _make_member(position=3)
        target.guild = guild
        bot = _make_member(position=2)
        bot.guild = guild
        guild.owner = MagicMock()

        result = _hierarchy_check(actor, bot, target)
        self.assertIsNotNone(result)
        self.assertIn("role", result.lower())

    def test_server_owner_as_actor_bypasses_rank_check(self) -> None:
        owner = _make_member(position=0, is_owner=True)
        target = _make_member(position=0)
        target.guild = owner.guild
        bot = _make_member(position=5)
        bot.guild = owner.guild

        self.assertIsNone(_hierarchy_check(owner.guild.owner, bot, target))

    def test_everyone_rank_equal_blocks_non_owner_actor(self) -> None:
        guild = MagicMock()
        actor = _make_member(position=0)
        actor.guild = guild
        target = _make_member(position=0)
        target.guild = guild
        bot = _make_member(position=5)
        bot.guild = guild
        guild.owner = MagicMock()

        result = _hierarchy_check(actor, bot, target)
        self.assertIsNotNone(result)

    def test_bot_equal_to_target_rank_blocked(self) -> None:
        guild = MagicMock()
        actor = _make_member(position=5)
        actor.guild = guild
        target = _make_member(position=3)
        target.guild = guild
        bot = _make_member(position=3)
        bot.guild = guild
        guild.owner = MagicMock()

        result = _hierarchy_check(actor, bot, target)
        self.assertIsNotNone(result)

    def test_server_owner_as_actor_still_blocked_when_bot_rank_too_low(self) -> None:
        """Owner bypass skips the actor check only — bot rank check is always enforced."""
        owner = _make_member(position=0, is_owner=True)
        target = _make_member(position=5)
        target.guild = owner.guild
        bot = _make_member(position=4)
        bot.guild = owner.guild

        result = _hierarchy_check(owner.guild.owner, bot, target)
        self.assertIsNotNone(result)

    def test_actor_exactly_one_above_target_allowed(self) -> None:
        """Strict ordering: rank(actor) = rank(target) + 1 should pass."""
        guild = MagicMock()
        actor = _make_member(position=4)
        actor.guild = guild
        target = _make_member(position=3)
        target.guild = guild
        bot = _make_member(position=10)
        bot.guild = guild
        guild.owner = MagicMock()

        self.assertIsNone(_hierarchy_check(actor, bot, target))

    def test_bot_exactly_one_above_target_allowed(self) -> None:
        """Bot rank check: rank(bot) = rank(target) + 1 should pass."""
        guild = MagicMock()
        actor = _make_member(position=10)
        actor.guild = guild
        target = _make_member(position=3)
        target.guild = guild
        bot = _make_member(position=4)
        bot.guild = guild
        guild.owner = MagicMock()

        self.assertIsNone(_hierarchy_check(actor, bot, target))

    def test_all_checks_at_minimum_passing_boundary(self) -> None:
        """All conditions satisfied by exactly 1 position — should be allowed."""
        guild = MagicMock()
        actor = _make_member(position=4)
        actor.guild = guild
        target = _make_member(position=3)
        target.guild = guild
        bot = _make_member(position=4)
        bot.guild = guild
        guild.owner = MagicMock()

        self.assertIsNone(_hierarchy_check(actor, bot, target))


class EmbedHelperTests(unittest.TestCase):
    def test_success_embed_is_green(self) -> None:
        embed = _success_embed("Done.")
        self.assertEqual(embed.color, discord.Color.green())

    def test_success_embed_contains_checkmark(self) -> None:
        embed = _success_embed("Done.")
        self.assertIn("✅", embed.description)

    def test_error_embed_is_red(self) -> None:
        embed = _error_embed("Something went wrong.")
        self.assertEqual(embed.color, discord.Color.red())

    def test_error_embed_contains_cross(self) -> None:
        embed = _error_embed("Something went wrong.")
        self.assertIn("❌", embed.description)


if __name__ == "__main__":
    unittest.main()
