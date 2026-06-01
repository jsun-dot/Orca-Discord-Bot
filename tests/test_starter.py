from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
root_str = str(ROOT)
if root_str not in sys.path:
    sys.path.insert(0, root_str)

from orca_bot.cogs.starter import (
    INNER_BANNER_LEFT_PADDING,
    INNER_BANNER_RIGHT_PADDING,
    INNER_BANNER_WIDTH,
    ONLINE_BANNER_TITLE,
    OUTER_BANNER_WIDTH,
    _build_centered_banner_line,
    _build_inner_banner_line,
    _visual_len,
)

EXPECTED_LINE_LEN = OUTER_BANNER_WIDTH + 2  # outer ║ chars on each side


class VisualLenTests(unittest.TestCase):
    def test_ascii_string_matches_len(self) -> None:
        self.assertEqual(_visual_len("hello"), len("hello"))

    def test_emoji_counts_as_two(self) -> None:
        self.assertEqual(_visual_len("🤖"), 2)

    def test_mixed_emoji_and_ascii(self) -> None:
        self.assertEqual(_visual_len("🤖 hi"), 5)  # 2 + 1 + 1 + 1

    def test_two_emoji_adds_two_extra(self) -> None:
        self.assertEqual(_visual_len("🤖🤖"), 4)

    def test_empty_string(self) -> None:
        self.assertEqual(_visual_len(""), 0)


class CenteredBannerLineTests(unittest.TestCase):
    def test_empty_line_correct_char_length(self) -> None:
        self.assertEqual(len(_build_centered_banner_line()), EXPECTED_LINE_LEN)

    def test_ascii_content_correct_char_length(self) -> None:
        self.assertEqual(len(_build_centered_banner_line("hello")), EXPECTED_LINE_LEN)

    def test_starts_and_ends_with_border_char(self) -> None:
        line = _build_centered_banner_line("test")
        self.assertEqual(line[0], "║")
        self.assertEqual(line[-1], "║")

    def test_emoji_title_correct_visual_width(self) -> None:
        line = _build_centered_banner_line(ONLINE_BANNER_TITLE)
        self.assertEqual(_visual_len(line), EXPECTED_LINE_LEN)

    def test_emoji_title_char_length_less_than_visual(self) -> None:
        line = _build_centered_banner_line(ONLINE_BANNER_TITLE)
        extra = _visual_len(ONLINE_BANNER_TITLE) - len(ONLINE_BANNER_TITLE)
        self.assertEqual(len(line), EXPECTED_LINE_LEN - extra)


class InnerBannerLineTests(unittest.TestCase):
    def _expected_len(self) -> int:
        # ║ + left_padding + left_char + INNER_BANNER_WIDTH + right_char + right_padding + ║
        return (
            1
            + INNER_BANNER_LEFT_PADDING
            + 1
            + INNER_BANNER_WIDTH
            + 1
            + INNER_BANNER_RIGHT_PADDING
            + 1
        )

    def test_border_line_correct_length(self) -> None:
        line = _build_inner_banner_line("╭", "─" * INNER_BANNER_WIDTH, "╮")
        self.assertEqual(len(line), self._expected_len())

    def test_text_line_correct_length(self) -> None:
        line = _build_inner_banner_line(
            "│", "  Time (US/Eastern): 2026-01-01 00:00:00", "│"
        )
        self.assertEqual(len(line), self._expected_len())

    def test_border_line_equals_outer_banner_width(self) -> None:
        line = _build_inner_banner_line("╭", "─" * INNER_BANNER_WIDTH, "╮")
        self.assertEqual(len(line), EXPECTED_LINE_LEN)

    def test_starts_and_ends_with_outer_border(self) -> None:
        line = _build_inner_banner_line("│", "  content", "│")
        self.assertEqual(line[0], "║")
        self.assertEqual(line[-1], "║")

    def test_short_content_is_padded_to_inner_width(self) -> None:
        line = _build_inner_banner_line("│", "  hi", "│")
        self.assertEqual(len(line), EXPECTED_LINE_LEN)


if __name__ == "__main__":
    unittest.main()
