"""yt-dlp source resolution and Discord embed helpers for Orca."""

from __future__ import annotations

import asyncio
import functools
from typing import Any

import discord
import yt_dlp as youtube_dl
from discord.ext import commands

HEADER_LINE_SEPARATOR = "\\r\\n"
YOUTUBE_ORIGIN = "https://www.youtube.com"
USER_AGENT_HEADER_NAMES = ("User-Agent", "User-agent")
YTDL_NOT_FOUND_MESSAGE = "Couldn't find anything that matches `{query}`"
YTDL_FETCH_FAILED_MESSAGE = "Couldn't fetch `{url}`"
YTDL_REGATHER_FAILED_MESSAGE = "Couldn't regather `{url}`"
NOW_PLAYING_TITLE = "Now Playing"
NOW_PLAYING_DESCRIPTION_TEMPLATE = "```css\n{title}\n```"
NOW_PLAYING_DURATION_LABEL = "Duration"
NOW_PLAYING_REQUESTER_LABEL = "Played by"

SEARCH_CACHE_MAX_SIZE = 256

YTDL_OPTIONS: dict[str, Any] = {
    "format": "bestaudio/best",
    "extractaudio": True,
    "audioformat": "mp3",
    "outtmpl": "%(extractor)s-%(id)s-%(title)s.%(ext)s",
    "restrictfilenames": True,
    "noplaylist": False,
    "nocheckcertificate": True,
    "ignoreerrors": False,
    "logtostderr": False,
    "quiet": True,
    "no_warnings": True,
    "default_search": "auto",
    "source_address": "0.0.0.0",
    "extractor_args": {"youtube": {"player_client": ["android", "web"]}},
}
FFMPEG_BEFORE_OPTIONS = (
    "-loglevel error "
    "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5 "
    "-rw_timeout 15000000"
)
FFMPEG_OPTIONS: dict[str, str] = {
    "before_options": FFMPEG_BEFORE_OPTIONS,
    "options": "-vn",
}


class VoiceError(Exception):
    """Raised when a voice playback operation fails."""


class YTDLError(Exception):
    """Raised when yt-dlp fails to resolve or refresh a source."""


def _build_header_arg(headers: dict[str, str]) -> str:
    """Return FFmpeg's CRLF-separated `-headers` argument payload."""

    lines: list[str] = []
    for key, value in headers.items():
        if value is None:
            continue
        stripped_key = str(key).strip()
        if not stripped_key:
            continue
        lines.append(f"{stripped_key}: {str(value).strip()}")

    return HEADER_LINE_SEPARATOR.join(lines) + HEADER_LINE_SEPARATOR


def _ffmpeg_before_options(
    base_before: str,
    info: dict[str, Any],
    webpage_url: str,
) -> str:
    """Build FFmpeg `before_options` using yt-dlp HTTP headers."""

    http_headers: dict[str, str] = dict(info.get("http_headers") or {})

    if webpage_url:
        http_headers.setdefault("Referer", webpage_url)
        http_headers.setdefault("Origin", YOUTUBE_ORIGIN)

    user_agent = None
    for header_name in USER_AGENT_HEADER_NAMES:
        user_agent = http_headers.pop(header_name, None) or user_agent

    referer = http_headers.get("Referer")

    before_parts: list[str] = []
    if user_agent:
        escaped_user_agent = str(user_agent).replace('"', '\\"')
        before_parts.append(f'-user_agent "{escaped_user_agent}"')

    if referer:
        escaped_referer = str(referer).replace('"', '\\"')
        before_parts.append(f'-referer "{escaped_referer}"')

    if http_headers:
        header_value = _build_header_arg(http_headers)
        escaped_headers = header_value.replace('"', '\\"')
        before_parts.append(f'-headers "{escaped_headers}"')

    normalized_base = base_before.strip()
    if normalized_base:
        before_parts.append(normalized_base)

    return " ".join(before_parts).strip()


def _extract_webpage_urls(data: dict[str, Any]) -> list[str]:
    """Return one or more webpage URLs from a yt-dlp search result."""

    entries = data.get("entries")
    if entries:
        return [
            entry["webpage_url"]
            for entry in entries
            if entry and entry.get("webpage_url")
        ]

    webpage_url = data.get("webpage_url")
    return [webpage_url] if webpage_url else []


def _iter_playable_entries(info: dict[str, Any]) -> list[dict[str, Any]]:
    """Return playable yt-dlp entries from a single info payload."""

    entries = info.get("entries")
    if entries:
        return [entry for entry in entries if entry]
    return [info]


def _build_ffmpeg_options(
    info: dict[str, Any],
    webpage_url: str,
) -> dict[str, str]:
    """Return FFmpeg options updated with request headers for a source."""

    ffmpeg_options = dict(FFMPEG_OPTIONS)
    ffmpeg_options["before_options"] = _ffmpeg_before_options(
        ffmpeg_options.get("before_options", ""),
        info,
        webpage_url,
    )
    return ffmpeg_options


class YTDLSource(discord.PCMVolumeTransformer):
    """YouTube audio source wrapper for playback and metadata access."""

    ytdl = youtube_dl.YoutubeDL(YTDL_OPTIONS)
    _search_cache: dict[str, list[str]] = {}

    def __init__(
        self,
        ctx: commands.Context,
        source: discord.FFmpegPCMAudio,
        *,
        data: dict[str, Any],
        volume: float = 0.5,
    ) -> None:
        """Store source metadata alongside the FFmpeg audio source."""

        super().__init__(source, volume)
        self.requester = ctx.author
        self.channel = ctx.channel
        self.data = data

        self.uploader = data.get("uploader")
        self.uploader_url = data.get("uploader_url")
        self.title = data.get("title")
        self.thumbnail = data.get("thumbnail")
        self.description = data.get("description")
        self.duration = self.parse_duration(int(data.get("duration") or 0))
        self.tags = data.get("tags")

        self.url = data.get("webpage_url")
        self.stream_url = data.get("url")
        self.http_headers = dict(data.get("http_headers") or {})

    def __str__(self) -> str:
        """Return a readable title and uploader string for the source."""

        return f"**{self.title}** by **{self.uploader}**"

    @classmethod
    async def create_source(
        cls,
        ctx: commands.Context,
        search: str,
        *,
        loop: asyncio.AbstractEventLoop | None = None,
    ) -> list[YTDLSource]:
        """Resolve a search query or URL into one or more playable sources."""

        loop = loop or asyncio.get_running_loop()

        if search in cls._search_cache and cls._search_cache[search]:
            webpage_urls = cls._search_cache[search]
        else:
            partial = functools.partial(
                cls.ytdl.extract_info,
                search,
                download=False,
                process=False,
            )
            data = await loop.run_in_executor(None, partial)
            if data is None:
                raise YTDLError(YTDL_NOT_FOUND_MESSAGE.format(query=search))

            webpage_urls = _extract_webpage_urls(data)
            if not webpage_urls:
                raise YTDLError(YTDL_NOT_FOUND_MESSAGE.format(query=search))

            if len(cls._search_cache) >= SEARCH_CACHE_MAX_SIZE:
                cls._search_cache.pop(next(iter(cls._search_cache)))
            cls._search_cache[search] = webpage_urls

        sources: list[YTDLSource] = []
        for url in webpage_urls:
            partial = functools.partial(
                cls.ytdl.extract_info,
                url,
                download=False,
            )
            info = await loop.run_in_executor(None, partial)
            if info is None:
                raise YTDLError(YTDL_FETCH_FAILED_MESSAGE.format(url=url))

            for entry in _iter_playable_entries(info):
                ffmpeg_options = _build_ffmpeg_options(
                    entry,
                    entry.get("webpage_url") or url,
                )
                sources.append(
                    cls(
                        ctx,
                        discord.FFmpegPCMAudio(
                            entry["url"],
                            **ffmpeg_options,
                        ),
                        data=entry,
                    )
                )

        return sources

    @classmethod
    async def regather_stream(
        cls,
        ctx: commands.Context,
        source: YTDLSource,
        *,
        loop: asyncio.AbstractEventLoop | None = None,
    ) -> YTDLSource:
        """Refresh an expiring stream URL and return a new playable source."""

        loop = loop or asyncio.get_running_loop()

        if not getattr(source, "url", None):
            return source

        partial = functools.partial(
            cls.ytdl.extract_info,
            source.url,
            download=False,
        )
        info = await loop.run_in_executor(None, partial)
        if info is None:
            raise YTDLError(
                YTDL_REGATHER_FAILED_MESSAGE.format(url=source.url)
            )

        entries = _iter_playable_entries(info)
        refreshed_info = entries[0]
        ffmpeg_options = _build_ffmpeg_options(
            refreshed_info,
            source.url,
        )

        return cls(
            ctx,
            discord.FFmpegPCMAudio(
                refreshed_info["url"],
                **ffmpeg_options,
            ),
            data=refreshed_info,
            volume=source.volume,
        )

    @staticmethod
    def parse_duration(duration: int) -> str:
        """Return a readable duration string from a number of seconds."""

        minutes, seconds = divmod(duration, 60)
        hours, minutes = divmod(minutes, 60)
        days, hours = divmod(hours, 24)

        duration_parts: list[str] = []
        if days > 0:
            duration_parts.append(f"{days} days")
        if hours > 0:
            duration_parts.append(f"{hours} hours")
        if minutes > 0:
            duration_parts.append(f"{minutes} minutes")
        if seconds > 0:
            duration_parts.append(f"{seconds} seconds")
        return ", ".join(duration_parts)


class Song:
    """Lightweight wrapper around a source and its requester."""

    __slots__ = ("source", "requester")

    def __init__(self, source: YTDLSource) -> None:
        """Store a playable source and the user who requested it."""

        self.source = source
        self.requester = source.requester

    def create_embed(self) -> discord.Embed:
        """Return the standard now-playing embed for the song."""

        embed = discord.Embed(
            title=NOW_PLAYING_TITLE,
            description=NOW_PLAYING_DESCRIPTION_TEMPLATE.format(
                title=self.source.title
            ),
            color=discord.Color.blue(),
        )
        embed.add_field(
            name=NOW_PLAYING_DURATION_LABEL,
            value=self.source.duration,
        )
        embed.add_field(
            name=NOW_PLAYING_REQUESTER_LABEL,
            value=self.requester.mention,
        )
        embed.set_thumbnail(url=self.source.thumbnail)
        return embed
