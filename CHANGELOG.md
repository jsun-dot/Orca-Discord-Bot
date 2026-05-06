# Changelog

This file tracks published versions of Orca Discord Bot. For the full release history, see the [GitHub Releases](https://github.com/jsun-dot/Orca-Discord-Bot/releases) page.

## Unreleased

- No unreleased entries yet.

## [v0.2.0](https://github.com/jsun-dot/Orca-Discord-Bot/releases/tag/v0.2.0) - 2026-05-06

### Added
- Runtime profiles: set `ORCA_PROFILE=dev` or `ORCA_PROFILE=default` to select which Discord token is used at startup, with clear error messages when credentials are missing.
- Interactive CLI console (`orca>` prompt) runs in a background thread while the bot is live; supports `help`, `status`, `exit`, and `restart` commands.
- Structured logging across all cogs and utilities via `logging.getLogger(__name__)`; output routes to both the console and a daily log file (`log_YYYY-MM-DD.txt`).
- Unit tests for credential resolution, logger configuration, restart argument handling, console status output, and search query sanitisation (21 tests total).

### Fixed
- `discord.voice_state` and `discord.player` INFO spam suppressed to WARNING; FFmpeg `-loglevel error` silences `[https] No trailing CRLF` stderr noise.
- `/join` always responded "I am already in your voice channel" even on a fresh connect.
- `VoiceState.last_activity` was set once at initialisation and never updated, making the inactivity timer stale.
- `YTDLSource._search_cache` was unbounded and could grow indefinitely; capped at 256 entries with oldest-first eviction.
- `bot.loop.create_task` calls replaced with `asyncio.ensure_future` (deprecated in discord.py 2.x).
- `datetime.utcnow()` replaced with `datetime.now(timezone.utc)` across all files (deprecated in Python 3.12).
- Stale `#discriminator` suffix removed from moderation and ping log messages (Discord removed discriminators in 2023).
- Redundant Spotify playlist success message removed; the loading embed already confirms completion.
- `log_*.txt` added to `.gitignore` so daily log files cannot be accidentally committed.

## [v0.1.1](https://github.com/jsun-dot/Orca-Discord-Bot/releases/tag/v0.1.1) - 2026-02-28

- Added governance and project policy docs: `CONTRIBUTING.md`, `SECURITY.md`, `PRIVACY.md`, and `ACCEPTABLE_USE.md`.
- Fixed the now-playing queue button to render the queue again after the controls persistence changes.
- Fixed inactivity disconnects so Orca announces why it left before stopping playback.

## [v0.1.0](https://github.com/jsun-dot/Orca-Discord-Bot/releases/tag/v0.1.0) - 2026-02-27

- First public release of Orca Discord Bot.
- Added hybrid slash/prefix music commands, queue controls, and moderation utilities.
- Fixed now-playing controls so they stay usable longer and fail more safely when stale.
- Expanded setup and runtime documentation for self-hosting.
