# Orca Discord Bot

Orca is a Discord bot centered on music playback, queue management, and a small set of utility and moderation commands. The project is written with `discord.py`, uses modular cogs, supports both slash commands and prefix commands, and can be installed as a Python package.

## Features

- Music playback from search terms, direct links, and playlists resolved through `yt-dlp`
- Spotify playlist import support
- Queue controls with Discord button views
- Hybrid commands: slash commands and backtick-prefixed text commands
- Basic moderation commands
- Simple CI on `main` via GitHub Actions

## Project Docs

- [CHANGELOG.md](CHANGELOG.md)
- [CONTRIBUTING.md](CONTRIBUTING.md)
- [SECURITY.md](SECURITY.md)
- [PRIVACY.md](PRIVACY.md)
- [ACCEPTABLE_USE.md](ACCEPTABLE_USE.md)

## Current Command Style

All bot commands are implemented as hybrid commands, so they can be used either as:

- Slash commands, for example `/play`
- Prefix commands, for example `` `play ``

The current text-command prefix is a backtick: `` ` ``

## Available Commands

### Music

- `/join`
- `/leave`
- `/play <search or url>`
- `/display`
- `/pause`
- `/resume`
- `/skip`
- `/queue [page]`
- `/shuffle`
- `/remove <index>`
- `/clear`

Aliases currently supported in code:

- `/leave` also supports `disconnect`
- `/display` also supports `current` and `playing`

### Utility

- `/ping`

### Moderation

- `/kick <user>`
- `/changerole <user> <role>`

Permission-sensitive commands:

- `pause` and `resume` require `Manage Server`
- `kick` requires `Kick Members`
- `changerole` requires `Manage Roles`

## Requirements

- Python 3.13 recommended
- FFmpeg installed and available on your `PATH`
- A Discord bot token
- A Discord application with the required intents enabled

Optional:

- Spotify developer credentials for Spotify playlist support

## Discord Application Setup

Create a bot application in the Discord Developer Portal and enable the privileged intents the bot currently expects. The current code uses `discord.Intents.all()`, so at minimum you should align the application with the bot configuration before running it.

If you plan to use prefix commands in addition to slash commands, make sure message content access is enabled for the bot where required.

## Installation

### 1. Clone the repository

```bash
git clone https://github.com/jsun-dot/Orca-Discord-Bot.git
cd Orca-Discord-Bot
```

### 2. Create and activate a virtual environment

```bash
python3 -m venv .venv
source .venv/bin/activate
```

On Windows PowerShell:

```powershell
py -m venv .venv
.venv\Scripts\Activate.ps1
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

For local development, an editable install is the cleanest option:

```bash
pip install -e .
```

### 4. Install FFmpeg

Orca uses FFmpeg for voice playback. Ensure the `ffmpeg` executable is available from your terminal before starting the bot.

You can verify it with:

```bash
ffmpeg -version
```

## Environment Variables

### Required

```env
DISCORD_TOKEN=your_bot_token_here
```

### Optional Spotify Support

Spotify playlist imports require both of the following:

```env
SPOTIPY_CLIENT_ID=your_spotify_client_id
SPOTIPY_CLIENT_SECRET=your_spotify_client_secret
```

## Configuration Notes

- `DISCORD_TOKEN` is required. The bot will exit on startup if it is missing.
- `.env` files are auto-loaded through `python-dotenv`.
- Spotify credentials are only required when using Spotify playlist URLs.
- The bot writes logs to `log_YYYY-MM-DD.txt` in the project root.

## Running the Bot

```bash
orca-bot
```

You can also run it directly from source:

```bash
python3 -m orca_bot
```

The legacy repo-root entry point still works as well:

```bash
python3 main.py
```

On startup, the bot:

- loads all cogs from the installed `orca_bot.cogs` package
- syncs slash commands
- writes logs to both the console and a dated log file

## Playback Notes

- `play` accepts plain search text and direct URLs supported by `yt-dlp`
- Spotify support is currently focused on playlist URLs
- Queue and now-playing messages are interactive and include playback controls
- The bot must be in the same voice channel as the requesting user for music commands

## Project Structure

```text
.
|-- main.py
|-- pyproject.toml
|-- orca_bot/
|   |-- __main__.py
|   |-- bot.py
|   |-- cogs/
|   |   |-- moderation.py
|   |   |-- music.py
|   |   |-- ping.py
|   |   `-- starter.py
|   `-- utils/
|       |-- views.py
|       |-- voice_state.py
|       `-- yt_source.py
`-- .github/
    |-- CODEOWNERS
    `-- workflows/
        `-- ci.yml
```

## Development

Main branch protection is now backed by a GitHub Actions workflow and `CODEOWNERS`.

The current CI check is a syntax compile pass equivalent to:

```bash
python3 -m compileall -q main.py orca_bot
```

If you are opening a PR, run that locally before pushing.

## Troubleshooting

### `Missing DISCORD_TOKEN`

Set `DISCORD_TOKEN` in your shell environment or place it in a local `.env` file.

### `ffmpeg` not found

Install FFmpeg and make sure the binary is available on your `PATH`.

### Spotify playlist command says Spotify is not configured

Set both `SPOTIPY_CLIENT_ID` and `SPOTIPY_CLIENT_SECRET`.

### Slash commands do not appear immediately

Slash command sync happens at startup. Give Discord a short time to propagate command updates after the bot connects.

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE).
