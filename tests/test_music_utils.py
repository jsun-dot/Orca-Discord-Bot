from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
root_str = str(ROOT)

if root_str not in sys.path:
    sys.path.insert(0, root_str)

from orca_bot.cogs.music import _sanitize_search_query


class SanitizeSearchQueryTests(unittest.TestCase):
    def test_removes_single_colon(self) -> None:
        self.assertEqual(_sanitize_search_query("hello:world"), "helloworld")

    def test_removes_multiple_colons(self) -> None:
        self.assertEqual(_sanitize_search_query("a:b:c"), "abc")

    def test_leaves_clean_query_unchanged(self) -> None:
        self.assertEqual(_sanitize_search_query("lofi hip hop"), "lofi hip hop")

    def test_empty_string_returns_empty(self) -> None:
        self.assertEqual(_sanitize_search_query(""), "")

    def test_url_like_input_strips_colons(self) -> None:
        self.assertEqual(
            _sanitize_search_query("https://youtube.com/watch?v=abc"),
            "https//youtube.com/watch?v=abc",
        )


if __name__ == "__main__":
    unittest.main()
