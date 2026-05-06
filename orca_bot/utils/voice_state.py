"""Voice state and queue management for Orca music playback."""

from __future__ import annotations

import asyncio
import itertools
import logging
import math
import random
from collections.abc import Iterator
from datetime import datetime, timezone

from async_timeout import timeout
import discord
from discord.ext import commands

from orca_bot.utils.views import NowPlayingButtons, QueuePages
from orca_bot.utils.yt_source import Song, YTDLSource

PLAYBACK_TIMEOUT_SEC = 1800
INACTIVITY_TIMEOUT_SEC = 1800
VOICE_RECONNECT_CHECK_INTERVAL_SEC = 0.5
DEFAULT_VOLUME = 0.3
QUEUE_ITEMS_PER_PAGE = 10
PERCENTAGE_MULTIPLIER = 100
ACTION_FIELD_NAME = "Action:"
QUEUE_EMPTY_DESCRIPTION = "**Empty queue.**"
QUEUE_DESCRIPTION_TEMPLATE = "**{count} track(s):**\n\n{queue}"
QUEUE_FOOTER_TEMPLATE = "Viewing page {page}/{pages}"
QUEUE_UPDATED_MESSAGE = "Queue updated."
QUEUE_STOPPED_MESSAGE = (
    "Bot disconnected from the voice channel. Stopping playback."
)
QUEUE_INACTIVITY_MESSAGE = (
    "Bot disconnected from the voice channel due to inactivity."
)
INACTIVITY_CHANNEL_NOTICE = "Leaving voice channel due to inactivity."
ADD_TO_QUEUE_MESSAGE = "Added to queue: **{title}**"

log = logging.getLogger(__name__)


class SongQueue(asyncio.Queue[Song]):
    """Async song queue with list-like helper methods."""

    def __getitem__(self, item: int | slice) -> Song | list[Song]:
        """Return a single item or a list of items from the queue."""

        if isinstance(item, slice):
            return list(
                itertools.islice(
                    self._queue,
                    item.start,
                    item.stop,
                    item.step,
                )
            )
        return self._queue[item]

    def __iter__(self) -> Iterator[Song]:
        """Iterate over the queued songs."""

        return iter(self._queue)

    def __len__(self) -> int:
        """Return the number of queued songs."""

        return self.qsize()

    def clear(self) -> None:
        """Remove all songs from the queue."""

        self._queue.clear()

    def shuffle(self) -> None:
        """Shuffle the queued songs in place."""

        random.shuffle(self._queue)

    def remove(self, index: int) -> None:
        """Remove a song at the provided queue index."""

        del self._queue[index]


class VoiceState:
    """Manage playback, queue state, and related UI for a guild."""

    def __init__(self, bot: commands.Bot, ctx: commands.Context) -> None:
        """Initialize the voice state for the current guild context."""

        self.bot = bot
        self._ctx = ctx
        self.text_channel = ctx.channel

        self.exists = True
        self.current: Song | None = None
        self.voice: discord.VoiceClient | None = None

        self.next = asyncio.Event()
        self.songs = SongQueue()

        self._loop = False
        self._volume = DEFAULT_VOLUME
        self.skip_votes: set[int] = set()

        self.audio_player: asyncio.Task[None] = asyncio.ensure_future(
            self.audio_player_task()
        )

        self.now_playing_message: discord.Message | None = None
        self.queue_message: discord.Message | None = None
        self.first_song_played = False
        self.action_message = ""

        self.inactivity_task: asyncio.Task[None] = asyncio.ensure_future(
            self.inactivity_timer()
        )
        self.lock = asyncio.Lock()
        self.last_activity = datetime.now(timezone.utc)
        self._stopping = False

    async def add_song(self, song: Song) -> None:
        """Add a song to the queue and restart the player task if needed."""

        await self.songs.put(song)
        self.last_activity = datetime.now(timezone.utc)
        await self.add_song_message(song)

        if not self.audio_player or self.audio_player.done():
            self.audio_player = asyncio.ensure_future(
                self.audio_player_task()
            )

    def __del__(self) -> None:
        """Cancel the audio task when the voice state is garbage collected."""

        try:
            if self.audio_player and not self.audio_player.done():
                self.audio_player.cancel()
        except Exception:
            pass

    @property
    def loop(self) -> bool:
        """Return whether the current track should loop."""

        return self._loop

    @loop.setter
    def loop(self, value: bool) -> None:
        """Enable or disable looping for the current track."""

        self._loop = value

    @property
    def volume(self) -> float:
        """Return the current playback volume."""

        return self._volume

    @volume.setter
    def volume(self, value: float) -> None:
        """Set the playback volume."""

        self._volume = value

    @property
    def is_playing(self) -> bool:
        """Return whether audio is actively playing."""

        return bool(self.voice and self.current and self.voice.is_playing())

    async def change_volume(
        self,
        delta: int,
        interaction: discord.Interaction,
    ) -> None:
        """Adjust the playback volume by the provided percentage delta."""

        new_volume = self._volume + (delta / PERCENTAGE_MULTIPLIER)
        self._volume = max(0, min(1, new_volume))
        if self.current is not None:
            self.current.source.volume = self._volume

        self.action_message = (
            f"**{interaction.user.display_name} changed the volume to "
            f"{int(self._volume * PERCENTAGE_MULTIPLIER)}%**"
        )
        await self.update_now_playing_embed(interaction)

    async def audio_player_task(self) -> None:
        """Continuously pull songs from the queue and play them."""

        while True:
            self.next.clear()

            if not self.loop or not self.current:
                try:
                    async with timeout(PLAYBACK_TIMEOUT_SEC):
                        self.current = await self.songs.get()
                        log.info("Playing song: %s", self.current.source.title)
                except asyncio.TimeoutError:
                    log.info("No more songs in the queue. Stopping playback.")
                    await self.stop(
                        queue_message_text=QUEUE_INACTIVITY_MESSAGE,
                        channel_notice=INACTIVITY_CHANNEL_NOTICE,
                    )
                    return

            if not self.voice or not self.voice.is_connected():
                await asyncio.sleep(VOICE_RECONNECT_CHECK_INTERVAL_SEC)
                continue

            try:
                self.current.source = await YTDLSource.regather_stream(
                    self._ctx,
                    self.current.source,
                )
            except Exception as error:
                log.warning(
                    "Failed to regather stream URL (will try old URL): %s",
                    error,
                )

            self.current.source.volume = self._volume
            self.voice.play(self.current.source, after=self.play_next_song)
            self.last_activity = datetime.now(timezone.utc)
            self.first_song_played = True
            await self.update_now_playing_embed()

            await self.next.wait()

            if self.loop and self.current:
                log.info("Looping the current song (replay without re-queue).")
            else:
                self.current = None

    def play_next_song(self, error: Exception | None = None) -> None:
        """Advance to the next song after playback finishes."""

        if error is not None:
            log.error("Playback error: %s", error)
        self.bot.loop.call_soon_threadsafe(self.next.set)

    def skip(self) -> None:
        """Skip the currently playing song."""

        self.skip_votes.clear()
        if self.is_playing:
            log.info("Skipping the current song...")
            self.voice.stop()

    def _build_queue_embeds(self) -> list[discord.Embed]:
        """Build paginated queue embeds for the current queue state."""

        if len(self.songs) == 0:
            return [discord.Embed(description=QUEUE_EMPTY_DESCRIPTION)]

        pages = max(1, math.ceil(len(self.songs) / QUEUE_ITEMS_PER_PAGE))
        embeds: list[discord.Embed] = []

        for page in range(pages):
            page_songs = self.songs[
                page * QUEUE_ITEMS_PER_PAGE : (page + 1) * QUEUE_ITEMS_PER_PAGE
            ]
            queue_lines = [
                f"`{index + 1}.` [**{song.source.title}**]({song.source.url})"
                for index, song in enumerate(
                    page_songs,
                    start=page * QUEUE_ITEMS_PER_PAGE,
                )
            ]
            queue_text = "\n".join(queue_lines)

            embed = discord.Embed(
                description=QUEUE_DESCRIPTION_TEMPLATE.format(
                    count=len(self.songs),
                    queue=queue_text,
                )
            )
            embed.set_footer(
                text=QUEUE_FOOTER_TEMPLATE.format(
                    page=page + 1,
                    pages=pages,
                )
            )
            embeds.append(embed)

        return embeds

    def _get_queue_channel(self):
        """Return the preferred channel for queue messages."""

        if self.queue_message is not None:
            return self.queue_message.channel
        if self.text_channel is not None:
            return self.text_channel
        return self._ctx.channel

    def _get_now_playing_channel(self):
        """Return the preferred channel for now-playing messages."""

        if self.now_playing_message is not None:
            return self.now_playing_message.channel
        if self.text_channel is not None:
            return self.text_channel
        return self._ctx.channel

    async def show_queue(self, page: int = 1) -> discord.Message | None:
        """Send or update the paginated queue message."""

        channel = self._get_queue_channel()
        if channel is None:
            return None

        embeds = self._build_queue_embeds()
        current_page = max(0, min(page - 1, len(embeds) - 1))
        view = QueuePages(self._ctx, embeds, current_page=current_page)

        try:
            if self.queue_message is not None:
                self.queue_message = await self.queue_message.edit(
                    embed=embeds[current_page],
                    view=view,
                )
            else:
                self.queue_message = await channel.send(
                    embed=embeds[current_page],
                    view=view,
                )
        except discord.NotFound:
            self.queue_message = await channel.send(
                embed=embeds[current_page],
                view=view,
            )
        except discord.HTTPException as error:
            if error.status == 401:
                log.error(
                    "Invalid Webhook Token. Unable to edit queue message."
                )
                self.queue_message = await channel.send(
                    embed=embeds[current_page],
                    view=view,
                )
            else:
                raise

        view.message = self.queue_message
        return self.queue_message

    async def stop(
        self,
        *,
        queue_message_text: str = QUEUE_STOPPED_MESSAGE,
        channel_notice: str | None = None,
    ) -> None:
        """Disconnect the bot and clean up queue-related messages."""

        if self._stopping:
            return

        self._stopping = True
        self.songs.clear()

        channel = self.text_channel or self._ctx.channel
        if (
            channel_notice
            and channel
            and self.voice
            and self.voice.is_connected()
        ):
            try:
                await channel.send(channel_notice)
            except Exception:
                pass

        if self.voice is not None:
            try:
                await self.voice.disconnect()
            except Exception:
                pass
            self.voice = None

        self.exists = False

        if self.now_playing_message is not None:
            try:
                await self.now_playing_message.edit(view=None)
            except Exception:
                pass
            self.now_playing_message = None

        if self.queue_message is not None:
            try:
                await self.queue_message.edit(
                    content=queue_message_text,
                    embed=None,
                    view=None,
                )
            except Exception:
                pass
            self.queue_message = None

    async def update_queue_message(self) -> None:
        """Refresh the queue message if playback has started."""

        if not self.first_song_played:
            return
        await self.show_queue(page=1)

    async def ensure_queue_message_valid(self) -> None:
        """Recreate the queue message if the previous one was lost."""

        if self.queue_message is not None:
            try:
                await self.queue_message.edit(content=QUEUE_UPDATED_MESSAGE)
            except discord.NotFound:
                self.queue_message = None
        await self.update_queue_message()

    async def update_now_playing_embed(
        self,
        _interaction: discord.Interaction | None = None,
    ) -> None:
        """Send or update the now-playing embed and controls."""

        if self.current is None:
            return

        embed = self.current.create_embed()
        if self.action_message:
            embed.add_field(
                name=ACTION_FIELD_NAME,
                value=self.action_message,
                inline=False,
            )

        channel = self._get_now_playing_channel()
        view = NowPlayingButtons(self._ctx)

        try:
            if self.now_playing_message is not None:
                self.now_playing_message = await channel.fetch_message(
                    self.now_playing_message.id
                )
                self.now_playing_message = await self.now_playing_message.edit(
                    embed=embed,
                    view=view,
                )
            else:
                self.now_playing_message = await channel.send(
                    embed=embed,
                    view=view,
                )
        except discord.HTTPException as error:
            log.error("Failed to edit message: %s", error)
            self.now_playing_message = await channel.send(
                embed=embed,
                view=view,
            )

        view.message = self.now_playing_message
        self.action_message = ""

    async def inactivity_timer(self) -> None:
        """Stop the bot after prolonged inactivity."""

        log.info("Inactivity timer started.")
        while self.exists:
            await asyncio.sleep(INACTIVITY_TIMEOUT_SEC)

            inactivity_seconds = (
                datetime.now(timezone.utc) - self.last_activity
            ).total_seconds()
            if inactivity_seconds < INACTIVITY_TIMEOUT_SEC:
                continue

            if not self.is_playing and len(self.songs) == 0:
                if self.voice is not None:
                    await self.stop(
                        queue_message_text=QUEUE_INACTIVITY_MESSAGE,
                        channel_notice=INACTIVITY_CHANNEL_NOTICE,
                    )
                    log.info(
                        "Inactivity timer ended: Bot stopped due to "
                        "inactivity."
                    )
                else:
                    log.info(
                        "Inactivity timer ended: Bot was not connected to a "
                        "voice channel."
                    )
            else:
                log.info(
                    "Inactivity timer refreshed: Bot is active, resetting "
                    "inactivity timer."
                )

    async def add_song_message(self, song: Song) -> None:
        """Send a best-effort queue addition message to the text channel."""

        channel = self.text_channel or self._ctx.channel
        if not channel:
            return

        try:
            await channel.send(
                ADD_TO_QUEUE_MESSAGE.format(title=song.source.title)
            )
        except Exception:
            pass
