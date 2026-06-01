# Privacy

## Summary

Orca Discord Bot is self-hosted software. The project maintainer does not operate a central bot service for this repository and does not receive analytics, telemetry, or usage logs from your deployment by default.

If you run Orca yourself, you are the operator of that deployment and you control its configuration, logs, hosting environment, and access to any data it processes.

## What the software may process

Depending on how you use the bot, a self-hosted Orca deployment may process:

- Discord account, server, channel, and message metadata needed to respond to commands
- Voice and playback state needed for music features
- Media URLs, search terms, and playlist references submitted by users
- Local log entries written by the operator's deployment

## Logging

Current versions of Orca write log files locally on the machine where the bot runs. Those logs are operator-controlled.

The maintainer of this repository does not automatically receive those logs.

## Third-party services

When enabled by the operator, Orca may send requests to third-party services that power bot functionality, such as:

- Discord
- YouTube or other media sources resolved through `yt-dlp`
- Spotify, when Spotify playlist support is configured

Those services operate under their own terms and privacy policies.

## Data collection by the maintainer

The maintainer does not intentionally collect personal data from self-hosted deployments through this repository or package by default.

## Future AI features

This project does not currently document an enabled `/ask` command or other OpenAI-backed prompt feature in the released code. If a future operator-enabled AI feature is added, this policy should be updated before release to describe what prompts are sent, to which provider, and under what configuration.

## Operator responsibility

If you deploy Orca for a Discord community, you are responsible for:

- deciding what data is logged or retained in your environment
- controlling access to your server, logs, and bot token
- complying with local law and the terms of any third-party services you use

## Contact

If you believe this document is inaccurate for a released version of Orca, open an issue or pull request describing the gap.
