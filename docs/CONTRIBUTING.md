# Contributing

Thanks for contributing to Orca Discord Bot.

## Development Setup

Clone the repository and create a virtual environment:

```bash
git clone https://github.com/jsun-dot/Orca-Discord-Bot.git
cd Orca-Discord-Bot
python3 -m venv .venv
source .venv/bin/activate
```

Install the project with dev dependencies:

```bash
make dev
```

Or directly:

```bash
pip install ".[dev]"
```

## Local Prerequisites

- Python 3.11 or newer
- FFmpeg on `PATH` for voice playback features
- A Discord bot token in your local environment or `.env`
- Spotify credentials only if you are testing Spotify playlist support

## Running the Bot

```bash
make run
# or with debug logging
make run-debug
```

From the repo root directly:

```bash
orca-bot
python3 -m orca_bot
python3 main.py
```

## CI Checks

Before opening a PR, run the full local check:

```bash
make test
make lint
```

CI runs on every PR and will fail if either step fails. If you change runtime behavior, also do the relevant manual checks locally. For example:

- music playback and queue commands
- now-playing button interactions
- slash-command sync after startup
- moderation commands in a test server

## Pull Request Expectations

- Keep changes focused and explain the user-visible impact clearly.
- Open PRs against `main`.
- Update docs when behavior, setup, or commands change.
- Do not commit secrets, `.env` files, local virtual environments, or build artifacts.
- Avoid committing generated files such as `__pycache__` or `.pyc` files.

If your change affects a release-worthy behavior, include a short release note summary in the PR description so it can be folded into the changelog or GitHub release notes later.

## Code Style

- Match the existing project structure and naming patterns.
- Keep comments concise and add them only where they clarify non-obvious logic.
- Prefer small, reviewable commits and straightforward code paths over broad refactors.

## Questions

If you are unsure about a change, open a draft PR or issue first so scope and direction can be discussed before you spend time on implementation.
