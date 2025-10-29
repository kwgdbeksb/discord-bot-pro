# Discord Bot Pro

A professional Discord bot featuring music playback with Wavelink/Lavalink, moderation helpers, games, and diagnostics. This repository is structured for easy deployment on panels and local development.

## Features
- Slash commands and prefix support
- Music playback powered by Wavelink + Lavalink
- Owner diagnostics with hourly status DM
- Audit logging of interactions and command usage
- Games (TicTacToe, Blackjack, Football) via cogs
- Resilient startup scripts for Windows (PowerShell) and Linux (bash)

## Quick Start
1. Create a `.env` from `.env.example` and fill `DISCORD_TOKEN`, `APP_ID`, `OWNER_ID`.
2. Ensure Java is installed if you plan to run a local Lavalink.
3. Run `start.ps1` on Windows or `start.sh` on Linux.

## Configuration
- Lavalink config is in `lavalink/application.yml`.
- Bot runtime config is loaded via `src/config.py` from environment variables.

## Requirements
See `requirements.txt` for Python dependencies.

---
This repository was initialized programmatically; more docs will be added as cogs are uploaded.