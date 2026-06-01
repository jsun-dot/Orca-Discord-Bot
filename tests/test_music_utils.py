from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
root_str = str(ROOT)

if root_str not in sys.path:
    sys.path.insert(0, root_str)

from orca_bot.cogs.music import _sanitize_search_query
from orca_bot.utils.yt_source import EQ_BANDS, FFMPEG_OPTIONS


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


class EqualizerTests(unittest.TestCase):
    def test_eq_bands_has_ten_bands(self) -> None:
        self.assertEqual(len(EQ_BANDS), 10)

    def test_eq_bands_frequencies_are_standard(self) -> None:
        freqs = [freq for freq, _ in EQ_BANDS]
        self.assertEqual(freqs, [32, 64, 125, 250, 500, 1000, 2000, 4000, 8000, 16000])

    def test_eq_bands_gains_are_within_ffmpeg_safe_range(self) -> None:
        for freq, gain in EQ_BANDS:
            self.assertGreaterEqual(gain, -12, f"{freq}Hz gain below -12dB")
            self.assertLessEqual(gain, 12, f"{freq}Hz gain above +12dB")

    def test_ffmpeg_options_include_equalizer_filter(self) -> None:
        self.assertIn("equalizer", FFMPEG_OPTIONS["options"])

    def test_ffmpeg_options_contain_all_bands(self) -> None:
        for freq, gain in EQ_BANDS:
            self.assertIn(f"f={freq}", FFMPEG_OPTIONS["options"])
            self.assertIn(f"g={gain}", FFMPEG_OPTIONS["options"])

    def test_ffmpeg_options_disable_video(self) -> None:
        self.assertIn("-vn", FFMPEG_OPTIONS["options"])


if __name__ == "__main__":
    unittest.main()
