"""Music playback commands and Spotify playlist handling for Orca."""

import asyncio
import logging
import math
import os
import time
from collections import defaultdict
from datetime import datetime, timezone

import discord
import requests
import spotipy
from discord.ext import commands
from spotipy.oauth2 import SpotifyClientCredentials

from orca_bot.utils.views import ClearQueueConfirmation
from orca_bot.utils.voice_state import VoiceState
from orca_bot.utils.yt_source import Song, YTDLError, YTDLSource

SPOTIFY_CLIENT_ID_ENV_VAR = "SPOTIPY_CLIENT_ID"
SPOTIFY_CLIENT_SECRET_ENV_VAR = "SPOTIPY_CLIENT_SECRET"
UTC_LOG_TIMESTAMP_FORMAT = "%Y-%m-%d %H:%M:%S UTC"
SEARCH_CLEANUP_TOKEN = ":"
SPOTIFY_PLAYLIST_URL_MARKER = "spotify.com/playlist"
SPOTIFY_PLAYLIST_NAME_FALLBACK = "Spotify playlist"
YOUTUBE_QUERY_SUFFIX = " Audio"
QUEUE_ITEMS_PER_PAGE = 10
SPOTIFY_PLAYLIST_RESOLVE_DELAY_SEC = 20
SPOTIFY_RESOLVE_CONCURRENCY = 2
SPOTIFY_RESOLVE_BATCH_SIZE = 10
PLAYLIST_PROGRESS_EDIT_INTERVAL_SEC = 2.5
QUEUE_UPDATE_BATCH_MULTIPLIER = 3

SpotifyTrack = tuple[str, str]

log = logging.getLogger(__name__)


def _utc_timestamp() -> str:
    """Return the current UTC timestamp for command usage logs."""

    return datetime.now(timezone.utc).strftime(UTC_LOG_TIMESTAMP_FORMAT)


def _sanitize_search_query(query: str) -> str:
    """Return a search query safe for downstream source resolution."""

    return query.replace(SEARCH_CLEANUP_TOKEN, "")


class Music(commands.Cog):
    """Music playback commands and Spotify playlist integration."""

    def __init__(self, bot: commands.Bot) -> None:
        """Initialize voice-state and playlist tracking for the cog."""

        self.bot = bot
        self.voice_states: dict[int, VoiceState] = {}
        self.processing_playlists: set[int] = set()
        self._playlist_locks = defaultdict(asyncio.Lock)
        self._spotify: spotipy.Spotify | None = None

    def _get_spotify(self) -> spotipy.Spotify:
        """Return a lazily initialized Spotify client."""

        if self._spotify is not None:
            return self._spotify

        try:
            from dotenv import load_dotenv  # type: ignore

            load_dotenv()
        except Exception:
            pass

        client_id = os.getenv(SPOTIFY_CLIENT_ID_ENV_VAR)
        client_secret = os.getenv(SPOTIFY_CLIENT_SECRET_ENV_VAR)

        if not client_id or not client_secret:
            raise commands.CommandError(
                "Spotify is not configured. Set "
                f"{SPOTIFY_CLIENT_ID_ENV_VAR} and "
                f"{SPOTIFY_CLIENT_SECRET_ENV_VAR} "
                "(or add them to a .env file) to use Spotify playlists."
            )

        self._spotify = spotipy.Spotify(
            auth_manager=SpotifyClientCredentials(
                client_id=client_id,
                client_secret=client_secret,
            ),
            requests_session=requests.Session(),
        )
        return self._spotify

    def get_voice_state(self, ctx: commands.Context) -> VoiceState:
        """Return the guild voice state and sync its voice client reference."""

        assert ctx.guild is not None

        state = self.voice_states.get(ctx.guild.id)
        if not state or not state.exists:
            state = VoiceState(self.bot, ctx)
            self.voice_states[ctx.guild.id] = state

        ctx.voice_state = state

        if ctx.voice_client and (
            state.voice is None or state.voice != ctx.voice_client
        ):
            state.voice = ctx.voice_client

        return state

    def cog_unload(self) -> None:
        """Stop active voice states when the cog unloads."""

        for state in self.voice_states.values():
            asyncio.ensure_future(state.stop())

    def cog_check(self, ctx: commands.Context) -> bool:
        """Reject commands invoked outside of guild channels."""

        if not ctx.guild:
            raise commands.NoPrivateMessage(
                "This command can't be used in DM channels."
            )
        return True

    async def cog_command_error(
        self,
        ctx: commands.Context,
        error: commands.CommandError,
    ) -> None:
        """Send command errors back to the invoking context."""

        await ctx.send(f"An error occurred: {error}")

    async def ensure_voice_state(self, ctx: commands.Context) -> None:
        """Validate the caller voice state and sync the guild voice state."""

        ctx.voice_state = self.get_voice_state(ctx)
        if not ctx.author.voice or not ctx.author.voice.channel:
            raise commands.CommandError(
                "You are not connected to any voice channel."
            )

        if (
            ctx.voice_client
            and ctx.voice_client.channel != ctx.author.voice.channel
        ):
            raise commands.CommandError("Orca is already in a voice channel.")

    async def _maybe_defer(self, ctx: commands.Context) -> None:
        """Defer slash-style invocations before longer operations."""

        interaction = getattr(ctx, "interaction", None)
        if interaction and not interaction.response.is_done():
            try:
                await ctx.defer(thinking=True)
            except Exception:
                pass

    async def _ensure_connected(
        self,
        ctx: commands.Context,
        destination: discord.abc.Connectable,
    ) -> discord.VoiceProtocol:
        """Ensure the bot is connected to the requested voice destination."""

        if ctx.voice_client:
            if not ctx.voice_client.is_connected():
                try:
                    await ctx.voice_client.disconnect(force=True)
                except Exception:
                    pass
                ctx.voice_state.voice = await destination.connect(
                    reconnect=True
                )
            else:
                ctx.voice_state.voice = ctx.voice_client
            return ctx.voice_state.voice

        if ctx.voice_state.voice and ctx.voice_state.voice.is_connected():
            return ctx.voice_state.voice

        ctx.voice_state.voice = await destination.connect(reconnect=True)
        return ctx.voice_state.voice

    def _log_command_usage(
        self,
        ctx: commands.Context,
        action: str,
        detail: str | None = None,
    ) -> None:
        """Write a standardized command usage log entry."""

        assert ctx.guild is not None

        suffix = f": {detail}" if detail else ""
        log.info(
            '%s - %s used %s in "%s" (%s)%s',
            _utc_timestamp(),
            ctx.author,
            action,
            ctx.guild.name,
            ctx.guild.id,
            suffix,
        )

    @commands.hybrid_command(
        name="join",
        description="Join a voice channel.",
        invoke_without_subcommand=True,
    )
    async def _join(self, ctx: commands.Context) -> None:
        """Join the caller's current voice channel."""

        await self.ensure_voice_state(ctx)
        await self._maybe_defer(ctx)

        destination = ctx.author.voice.channel
        was_connected = bool(ctx.voice_client and ctx.voice_client.is_connected())
        await self._ensure_connected(ctx, destination)

        msg = (
            "I am already in your voice channel."
            if was_connected
            else "I joined your voice channel."
        )
        await ctx.send(msg)

        self._log_command_usage(ctx, "join")

    @commands.hybrid_command(
        name="leave",
        description="Leave the voice channel.",
        aliases=["disconnect"],
    )
    async def _leave(self, ctx: commands.Context) -> None:
        """Leave the current voice channel and clear guild voice state."""

        await self.ensure_voice_state(ctx)
        await self._maybe_defer(ctx)

        if not (ctx.voice_state.voice or ctx.voice_client):
            await ctx.send("Not connected to a voice channel.")
            return

        assert ctx.guild is not None

        await ctx.voice_state.stop()
        self.voice_states.pop(ctx.guild.id, None)

        self._log_command_usage(ctx, "leave")
        await ctx.send("Left the voice channel.")

    @commands.hybrid_command(
        name="display",
        description="Displays the currently playing song.",
        aliases=["current", "playing"],
    )
    async def _now(self, ctx: commands.Context) -> None:
        """Display the song currently being played."""

        await self.ensure_voice_state(ctx)
        await self._maybe_defer(ctx)

        if not ctx.voice_state.current:
            await ctx.send("Nothing is playing right now.")
            return

        await ctx.send(embed=ctx.voice_state.current.create_embed())

    @commands.hybrid_command(name="pause", description="Pauses the audio.")
    @commands.has_permissions(manage_guild=True)
    async def _pause(self, ctx: commands.Context) -> None:
        """Pause the current audio stream."""

        await self.ensure_voice_state(ctx)
        await self._maybe_defer(ctx)

        player = ctx.voice_client
        if player and player.is_playing():
            player.pause()
            await ctx.send("I paused the audio.")
        else:
            await ctx.send("No audio is playing currently.")

    @commands.hybrid_command(name="resume", description="Resume the audio")
    @commands.has_permissions(manage_guild=True)
    async def _resume(self, ctx: commands.Context) -> None:
        """Resume a paused audio stream."""

        await self.ensure_voice_state(ctx)
        await self._maybe_defer(ctx)

        player = ctx.voice_client
        if player and player.is_paused():
            player.resume()
            await ctx.send("I resumed the audio.")
        else:
            await ctx.send("The audio is already playing.")

    @commands.hybrid_command(
        name="skip",
        description="Skips the currently playing audio.",
    )
    async def _skip(self, ctx: commands.Context) -> None:
        """Skip the currently playing audio source."""

        await self.ensure_voice_state(ctx)
        await self._maybe_defer(ctx)

        if not ctx.voice_state.is_playing:
            await ctx.send("No audio is playing.")
            return

        ctx.voice_state.skip()
        await ctx.send("Skipped the audio.")

    @commands.hybrid_command(
        name="queue",
        description=(
            "Shows the queue. You can optionally specify the page to show. "
            "Each page contains 10 elements."
        ),
    )
    async def _queue(self, ctx: commands.Context, *, page: int = 1) -> None:
        """Display the current queue page."""

        await self.ensure_voice_state(ctx)
        await self._maybe_defer(ctx)

        if len(ctx.voice_state.songs) == 0:
            await ctx.send("Empty queue.")
            return

        pages = max(
            1,
            math.ceil(len(ctx.voice_state.songs) / QUEUE_ITEMS_PER_PAGE),
        )
        requested_page = max(1, min(page, pages))
        await ctx.voice_state.show_queue(requested_page)

    @commands.hybrid_command(name="clear", description="Clears the queue.")
    async def _clear(self, ctx: commands.Context) -> None:
        """Prompt for confirmation and clear the queue."""

        await self.ensure_voice_state(ctx)
        await self._maybe_defer(ctx)

        if len(ctx.voice_state.songs) == 0:
            await ctx.send("The queue is already empty.")
            return

        view = ClearQueueConfirmation(ctx, ctx.voice_state)
        view.message = await ctx.send(
            "Are you sure you want to clear the queue?",
            view=view,
        )

    @commands.hybrid_command(name="shuffle", description="Shuffles the queue.")
    async def _shuffle(self, ctx: commands.Context) -> None:
        """Shuffle the current queue."""

        await self.ensure_voice_state(ctx)
        await self._maybe_defer(ctx)

        if len(ctx.voice_state.songs) == 0:
            await ctx.send("Empty queue.")
            return

        ctx.voice_state.songs.shuffle()
        await ctx.voice_state.update_queue_message()
        await ctx.send("I shuffled the queue.")

    @commands.hybrid_command(
        name="remove",
        description="Removes audio from the queue at a given index.",
    )
    async def _remove(self, ctx: commands.Context, index: int) -> None:
        """Remove a queued item by one-based index."""

        await self.ensure_voice_state(ctx)
        await self._maybe_defer(ctx)

        queue_length = len(ctx.voice_state.songs)
        if queue_length == 0:
            await ctx.send("Empty queue.")
            return

        if index < 1 or index > queue_length:
            await ctx.send(
                f"Invalid index. Choose a number from 1 to {queue_length}."
            )
            return

        ctx.voice_state.songs.remove(index - 1)
        await ctx.voice_state.update_queue_message()
        await ctx.send(f"Removed item #{index} from the queue.")

    @commands.hybrid_command(name="play", description="Plays audio.")
    async def _play(self, ctx: commands.Context, *, search: str) -> None:
        """Resolve audio sources and enqueue them for playback."""

        await self.ensure_voice_state(ctx)
        await self._maybe_defer(ctx)

        destination = ctx.author.voice.channel
        await self._ensure_connected(ctx, destination)

        self._log_command_usage(ctx, "play", search)

        try:
            async with ctx.typing():
                if SPOTIFY_PLAYLIST_URL_MARKER in search:
                    try:
                        await self.play_spotify_playlist(ctx, search)
                    except commands.CommandError as error:
                        await ctx.send(str(error))
                    return

                search = _sanitize_search_query(search)
                sources = await YTDLSource.create_source(
                    ctx,
                    search,
                )
                if not sources:
                    await ctx.send("No results found.")
                    return

                async with ctx.voice_state.lock:
                    if len(sources) > 1:
                        for source in sources:
                            await ctx.voice_state.songs.put(Song(source))
                        ctx.voice_state.action_message = (
                            f"{ctx.author.display_name} added a playlist to "
                            "the queue."
                        )
                    else:
                        song = Song(sources[0])
                        await ctx.voice_state.songs.put(song)
                        ctx.voice_state.action_message = (
                            f"{ctx.author.display_name} added "
                            f"{song.source.title} by {song.source.uploader}."
                        )

                await ctx.voice_state.update_now_playing_embed()

            await ctx.send("Your request has been added to the queue.")

        except YTDLError as error:
            log.error("YTDLError: %s", error)
            await ctx.send(
                f"An error occurred while processing this request: {error}"
            )
        except Exception as error:
            log.exception("Unexpected error in play: %s", error)
            await ctx.send(f"An unexpected error occurred: {error}")

    async def _fetch_spotify_playlist(
        self,
        playlist_id: str,
    ) -> tuple[str, list[SpotifyTrack]]:
        """Fetch a Spotify playlist name and track list in a worker thread."""

        def _run() -> tuple[str, list[SpotifyTrack]]:
            spotify_client = self._get_spotify()
            playlist = spotify_client.playlist(playlist_id)
            name = playlist.get("name", SPOTIFY_PLAYLIST_NAME_FALLBACK)

            tracks: list[SpotifyTrack] = []
            results = spotify_client.playlist_tracks(playlist_id)

            while True:
                for item in results.get("items", []):
                    track = item.get("track")
                    if not track or track.get("is_local"):
                        continue

                    artists = track.get("artists") or []
                    artist_name = artists[0].get("name") if artists else ""
                    tracks.append((track.get("name") or "", artist_name))

                if results.get("next"):
                    results = spotify_client.next(results)
                else:
                    break

            return name, tracks

        return await asyncio.to_thread(_run)

    async def play_spotify_playlist(
        self,
        ctx: commands.Context,
        url: str,
    ) -> None:
        """Resolve and enqueue a Spotify playlist in track order."""

        assert ctx.guild is not None

        guild_id = ctx.guild.id
        playlist_id = url.split("/")[-1].split("?")[0]
        queue_update_interval = (
            SPOTIFY_RESOLVE_BATCH_SIZE * QUEUE_UPDATE_BATCH_MULTIPLIER
        )

        async with self._playlist_locks[guild_id]:
            self.processing_playlists.add(guild_id)
            try:
                voice_client = ctx.voice_client or ctx.voice_state.voice
                if not voice_client or not voice_client.is_connected():
                    await ctx.send("I'm not connected to a voice channel.")
                    return

                playlist_name, tracks = await self._fetch_spotify_playlist(
                    playlist_id
                )

                loading_message = await ctx.send(
                    embed=discord.Embed(
                        description=(
                            "Adding songs from the Spotify playlist "
                            f"**{playlist_name}**... "
                            ":arrows_counterclockwise:"
                        ),
                        color=discord.Color.orange(),
                    )
                )

                semaphore = asyncio.Semaphore(SPOTIFY_RESOLVE_CONCURRENCY)
                rate_limit_lock = asyncio.Lock()
                last_request = 0.0
                last_edit = 0.0

                async def resolve_one(
                    track_index: int,
                    name: str,
                    artist: str,
                ):
                    query = _sanitize_search_query(
                        f"{name} {artist}{YOUTUBE_QUERY_SUFFIX}"
                    )
                    async with semaphore:
                        nonlocal last_request
                        async with rate_limit_lock:
                            now = time.monotonic()
                            wait_time = max(
                                0.0,
                                SPOTIFY_PLAYLIST_RESOLVE_DELAY_SEC
                                - (now - last_request),
                            )
                            if wait_time:
                                await asyncio.sleep(wait_time)
                            last_request = time.monotonic()
                        try:
                            sources = await YTDLSource.create_source(
                                ctx,
                                query,
                            )
                            return track_index, sources, None
                        except Exception as error:
                            return track_index, None, error

                total = len(tracks)
                added = 0

                for start in range(0, total, SPOTIFY_RESOLVE_BATCH_SIZE):
                    voice_client = ctx.voice_client or ctx.voice_state.voice
                    if not voice_client or not voice_client.is_connected():
                        try:
                            await loading_message.edit(
                                embed=discord.Embed(
                                    description=(
                                        "Bot disconnected from the voice "
                                        "channel. Stopping playlist "
                                        "processing."
                                    ),
                                    color=discord.Color.red(),
                                )
                            )
                        except Exception:
                            pass
                        return

                    batch = tracks[start : start + SPOTIFY_RESOLVE_BATCH_SIZE]
                    tasks = [
                        resolve_one(start + index, name, artist)
                        for index, (name, artist) in enumerate(batch)
                    ]
                    results = await asyncio.gather(*tasks)
                    results.sort(key=lambda item: item[0])

                    async with ctx.voice_state.lock:
                        for track_index, sources, error in results:
                            if error or not sources:
                                log.warning(
                                    "Failed to resolve Spotify track %s/%s: "
                                    "%s",
                                    track_index + 1,
                                    total,
                                    error,
                                )
                                continue

                            if len(sources) > 1:
                                for source in sources:
                                    await ctx.voice_state.songs.put(
                                        Song(source)
                                    )
                                    added += 1
                            else:
                                await ctx.voice_state.songs.put(
                                    Song(sources[0])
                                )
                                added += 1

                    now = time.monotonic()
                    if now - last_edit > PLAYLIST_PROGRESS_EDIT_INTERVAL_SEC:
                        last_edit = now
                        processed = min(
                            start + SPOTIFY_RESOLVE_BATCH_SIZE,
                            total,
                        )
                        try:
                            await loading_message.edit(
                                embed=discord.Embed(
                                    description=(
                                        "Adding songs from the Spotify "
                                        "playlist "
                                        f"**{playlist_name}**... "
                                        f"({processed}/{total}) "
                                        ":arrows_counterclockwise:"
                                    ),
                                    color=discord.Color.orange(),
                                )
                            )
                        except Exception:
                            pass

                    if getattr(
                        ctx.voice_state,
                        "first_song_played",
                        False,
                    ) and (start % queue_update_interval == 0):
                        try:
                            await ctx.voice_state.update_queue_message()
                        except Exception:
                            pass

                ctx.voice_state.action_message = (
                    f"{ctx.author.display_name} added Spotify playlist "
                    f"**{playlist_name}** ({added} tracks)."
                )
                try:
                    await ctx.voice_state.update_queue_message()
                except Exception:
                    pass

                try:
                    await loading_message.edit(
                        embed=discord.Embed(
                            description=(
                                f"Added **{added}** track(s) from Spotify "
                                f"playlist **{playlist_name}**."
                            ),
                            color=discord.Color.green(),
                        )
                    )
                except Exception:
                    pass

            finally:
                self.processing_playlists.discard(guild_id)


async def setup(bot: commands.Bot) -> None:
    """Register the music cog with the bot."""

    await bot.add_cog(Music(bot))
