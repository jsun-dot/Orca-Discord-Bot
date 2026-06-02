from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
root_str = str(ROOT)
if root_str not in sys.path:
    sys.path.insert(0, root_str)

from orca_bot.cogs.utility import (
    EIGHT_BALL_NEGATIVE,
    EIGHT_BALL_NEUTRAL,
    EIGHT_BALL_POSITIVE,
    COINFLIP_OUTCOMES,
    ROLL_MAX_DICE,
    ROLL_MAX_SIDES,
    ROLL_PATTERN,
    _eight_ball_colour,
    _format_timestamp,
)
import discord
from datetime import datetime, timezone


class EightBallColourTests(unittest.TestCase):
    def test_positive_response_returns_green(self) -> None:
        for response in EIGHT_BALL_POSITIVE:
            self.assertEqual(_eight_ball_colour(response), discord.Color.green())

    def test_neutral_response_returns_grey(self) -> None:
        for response in EIGHT_BALL_NEUTRAL:
            self.assertEqual(_eight_ball_colour(response), discord.Color.greyple())

    def test_negative_response_returns_red(self) -> None:
        for response in EIGHT_BALL_NEGATIVE:
            self.assertEqual(_eight_ball_colour(response), discord.Color.red())

    def test_total_response_count_is_twenty(self) -> None:
        total = (
            len(EIGHT_BALL_POSITIVE)
            + len(EIGHT_BALL_NEUTRAL)
            + len(EIGHT_BALL_NEGATIVE)
        )
        self.assertEqual(total, 20)


class CoinflipTests(unittest.TestCase):
    def test_only_heads_or_tails(self) -> None:
        self.assertEqual(set(COINFLIP_OUTCOMES), {"Heads", "Tails"})

    def test_exactly_two_outcomes(self) -> None:
        self.assertEqual(len(COINFLIP_OUTCOMES), 2)


class FormatTimestampTests(unittest.TestCase):
    def test_returns_unknown_for_none(self) -> None:
        self.assertEqual(_format_timestamp(None), "Unknown")

    def test_returns_discord_timestamp_format(self) -> None:
        dt = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        result = _format_timestamp(dt)
        self.assertTrue(result.startswith("<t:"))
        self.assertTrue(result.endswith(":F>"))

    def test_naive_datetime_treated_as_utc(self) -> None:
        naive = datetime(2026, 1, 1, 0, 0, 0)
        aware = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        self.assertEqual(_format_timestamp(naive), _format_timestamp(aware))


class RollPatternTests(unittest.TestCase):
    def test_valid_notation_matches(self) -> None:
        self.assertIsNotNone(ROLL_PATTERN.match("2d6"))
        self.assertIsNotNone(ROLL_PATTERN.match("1d20"))
        self.assertIsNotNone(ROLL_PATTERN.match("10d10"))

    def test_case_insensitive(self) -> None:
        self.assertIsNotNone(ROLL_PATTERN.match("2D6"))

    def test_invalid_notation_does_not_match(self) -> None:
        self.assertIsNone(ROLL_PATTERN.match("d6"))
        self.assertIsNone(ROLL_PATTERN.match("2d"))
        self.assertIsNone(ROLL_PATTERN.match("roll"))
        self.assertIsNone(ROLL_PATTERN.match("2 d 6"))

    def test_extracts_count_and_sides(self) -> None:
        match = ROLL_PATTERN.match("3d8")
        self.assertEqual(int(match.group(1)), 3)
        self.assertEqual(int(match.group(2)), 8)

    def test_max_dice_and_sides_constants_are_reasonable(self) -> None:
        self.assertGreater(ROLL_MAX_DICE, 0)
        self.assertGreater(ROLL_MAX_SIDES, 1)


if __name__ == "__main__":
    unittest.main()
