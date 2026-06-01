from __future__ import annotations

import asyncio
import collections
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

ROOT = Path(__file__).resolve().parent.parent
root_str = str(ROOT)
if root_str not in sys.path:
    sys.path.insert(0, root_str)

from orca_bot.cogs.music import Music, SPOTIFY_PLAYLIST_RESOLVE_DELAY_SEC


def _make_mock_source(title: str = "Track") -> MagicMock:
    source = MagicMock()
    source.title = title
    source.uploader = "Artist"
    source.requester = MagicMock()
    return source


def _make_ctx(voice_connected: bool = True) -> MagicMock:
    ctx = MagicMock()
    ctx.guild = MagicMock()
    ctx.guild.id = 99999
    ctx.author.display_name = "TestUser"

    if voice_connected:
        ctx.voice_client = MagicMock()
        ctx.voice_client.is_connected.return_value = True
    else:
        ctx.voice_client = None

    ctx.voice_state = MagicMock()
    ctx.voice_state.lock = asyncio.Lock()
    ctx.voice_state.songs.put = AsyncMock()
    ctx.voice_state.first_song_played = False
    ctx.voice_state.update_queue_message = AsyncMock()
    ctx.voice_state.update_now_playing_embed = AsyncMock()
    ctx.voice_state.voice = MagicMock()
    ctx.voice_state.voice.is_connected.return_value = voice_connected

    mock_message = MagicMock()
    mock_message.edit = AsyncMock()
    ctx.send = AsyncMock(return_value=mock_message)

    return ctx


def _make_cog() -> Music:
    cog = Music.__new__(Music)
    cog.bot = MagicMock()
    cog.voice_states = {}
    cog.processing_playlists = set()
    cog._playlist_locks = collections.defaultdict(asyncio.Lock)
    cog._spotify = None
    return cog


class SpotifyUrlParsingTests(unittest.TestCase):
    def _parse(self, url: str) -> str:
        return url.split("/")[-1].split("?")[0]

    def test_standard_url(self) -> None:
        self.assertEqual(
            self._parse("https://open.spotify.com/playlist/37i9dQZEVXbMDoHDwVN2tF"),
            "37i9dQZEVXbMDoHDwVN2tF",
        )

    def test_url_with_si_query_param(self) -> None:
        self.assertEqual(
            self._parse(
                "https://open.spotify.com/playlist/37i9dQZEVXbMDoHDwVN2tF?si=abc123"
            ),
            "37i9dQZEVXbMDoHDwVN2tF",
        )

    def test_url_with_multiple_query_params(self) -> None:
        self.assertEqual(
            self._parse(
                "https://open.spotify.com/playlist/37i9dQZEVXbMDoHDwVN2tF?si=abc&context=xyz"
            ),
            "37i9dQZEVXbMDoHDwVN2tF",
        )


class SpotifyPlaylistResolutionTests(unittest.IsolatedAsyncioTestCase):
    async def test_each_track_enqueued_immediately_after_resolving(self) -> None:
        cog = _make_cog()
        ctx = _make_ctx()
        tracks = [
            ("Song A", "Artist A"),
            ("Song B", "Artist B"),
            ("Song C", "Artist C"),
        ]
        sources = [[_make_mock_source(t)] for t in ["Song A", "Song B", "Song C"]]

        with patch.object(
            cog,
            "_fetch_spotify_playlist",
            new=AsyncMock(return_value=("Test Playlist", tracks)),
        ):
            with patch(
                "orca_bot.cogs.music.YTDLSource.create_source",
                new=AsyncMock(side_effect=sources),
            ):
                with patch("asyncio.sleep", new=AsyncMock()):
                    await cog.play_spotify_playlist(
                        ctx, "https://open.spotify.com/playlist/abc123"
                    )

        self.assertEqual(ctx.voice_state.songs.put.call_count, 3)

    async def test_first_track_has_no_rate_limit_wait(self) -> None:
        cog = _make_cog()
        ctx = _make_ctx()
        tracks = [("Song A", "Artist A")]
        sources = [[_make_mock_source("Song A")]]
        sleep_calls: list[float] = []

        async def mock_sleep(seconds: float) -> None:
            sleep_calls.append(seconds)

        with patch.object(
            cog,
            "_fetch_spotify_playlist",
            new=AsyncMock(return_value=("Test Playlist", tracks)),
        ):
            with patch(
                "orca_bot.cogs.music.YTDLSource.create_source",
                new=AsyncMock(side_effect=sources),
            ):
                with patch("asyncio.sleep", side_effect=mock_sleep):
                    await cog.play_spotify_playlist(
                        ctx, "https://open.spotify.com/playlist/abc123"
                    )

        self.assertEqual(len(sleep_calls), 0)

    async def test_second_track_applies_rate_limit_delay(self) -> None:
        cog = _make_cog()
        ctx = _make_ctx()
        tracks = [("Song A", "Artist A"), ("Song B", "Artist B")]
        sources = [[_make_mock_source(t)] for t in ["Song A", "Song B"]]
        sleep_calls: list[float] = []

        async def mock_sleep(seconds: float) -> None:
            sleep_calls.append(seconds)

        with patch.object(
            cog,
            "_fetch_spotify_playlist",
            new=AsyncMock(return_value=("Test Playlist", tracks)),
        ):
            with patch(
                "orca_bot.cogs.music.YTDLSource.create_source",
                new=AsyncMock(side_effect=sources),
            ):
                with patch("asyncio.sleep", side_effect=mock_sleep):
                    await cog.play_spotify_playlist(
                        ctx, "https://open.spotify.com/playlist/abc123"
                    )

        self.assertEqual(len(sleep_calls), 1)
        self.assertAlmostEqual(
            sleep_calls[0], SPOTIFY_PLAYLIST_RESOLVE_DELAY_SEC, delta=1.0
        )

    async def test_failed_track_is_skipped_and_others_still_enqueue(self) -> None:
        cog = _make_cog()
        ctx = _make_ctx()
        tracks = [
            ("Song A", "Artist A"),
            ("Song B", "Artist B"),
            ("Song C", "Artist C"),
        ]

        async def mock_create_source(ctx_arg: MagicMock, query: str):
            if "Song B" in query:
                raise Exception("yt-dlp failed")
            return [_make_mock_source(query.split()[0])]

        with patch.object(
            cog,
            "_fetch_spotify_playlist",
            new=AsyncMock(return_value=("Test Playlist", tracks)),
        ):
            with patch(
                "orca_bot.cogs.music.YTDLSource.create_source",
                side_effect=mock_create_source,
            ):
                with patch("asyncio.sleep", new=AsyncMock()):
                    await cog.play_spotify_playlist(
                        ctx, "https://open.spotify.com/playlist/abc123"
                    )

        self.assertEqual(ctx.voice_state.songs.put.call_count, 2)

    async def test_disconnection_mid_playlist_stops_processing(self) -> None:
        cog = _make_cog()
        ctx = _make_ctx()
        tracks = [
            ("Song A", "Artist A"),
            ("Song B", "Artist B"),
            ("Song C", "Artist C"),
        ]
        put_count = 0

        async def mock_put(song: MagicMock) -> None:
            nonlocal put_count
            put_count += 1
            if put_count == 1:
                ctx.voice_client = None
                ctx.voice_state.voice = None

        ctx.voice_state.songs.put = mock_put

        async def mock_create_source(ctx_arg: MagicMock, query: str):
            return [_make_mock_source(query.split()[0])]

        with patch.object(
            cog,
            "_fetch_spotify_playlist",
            new=AsyncMock(return_value=("Test Playlist", tracks)),
        ):
            with patch(
                "orca_bot.cogs.music.YTDLSource.create_source",
                side_effect=mock_create_source,
            ):
                with patch("asyncio.sleep", new=AsyncMock()):
                    await cog.play_spotify_playlist(
                        ctx, "https://open.spotify.com/playlist/abc123"
                    )

        self.assertEqual(put_count, 1)

    async def test_update_now_playing_embed_called_after_playlist_loads(self) -> None:
        cog = _make_cog()
        ctx = _make_ctx()
        tracks = [("Song A", "Artist A")]
        sources = [[_make_mock_source("Song A")]]

        with patch.object(
            cog,
            "_fetch_spotify_playlist",
            new=AsyncMock(return_value=("Test Playlist", tracks)),
        ):
            with patch(
                "orca_bot.cogs.music.YTDLSource.create_source",
                new=AsyncMock(side_effect=sources),
            ):
                with patch("asyncio.sleep", new=AsyncMock()):
                    await cog.play_spotify_playlist(
                        ctx, "https://open.spotify.com/playlist/abc123"
                    )

        ctx.voice_state.update_now_playing_embed.assert_called_once()

    async def test_action_message_set_with_playlist_name_and_count(self) -> None:
        cog = _make_cog()
        ctx = _make_ctx()
        tracks = [("Song A", "Artist A"), ("Song B", "Artist B")]
        sources = [[_make_mock_source(t)] for t in ["Song A", "Song B"]]

        with patch.object(
            cog,
            "_fetch_spotify_playlist",
            new=AsyncMock(return_value=("My Playlist", tracks)),
        ):
            with patch(
                "orca_bot.cogs.music.YTDLSource.create_source",
                new=AsyncMock(side_effect=sources),
            ):
                with patch("asyncio.sleep", new=AsyncMock()):
                    await cog.play_spotify_playlist(
                        ctx, "https://open.spotify.com/playlist/abc123"
                    )

        self.assertIn("My Playlist", ctx.voice_state.action_message)
        self.assertIn("2", ctx.voice_state.action_message)


if __name__ == "__main__":
    unittest.main()
