import os
from dataclasses import dataclass


@dataclass
class BotConfig:
    token: str
    app_id: int
    owner_id: int
    guild_id: int | None
    sync_global: bool
    yt_cookies: str | None
    lavalink_host: str
    lavalink_port: int
    lavalink_password: str


def load_config() -> BotConfig:
    # Allow environment variables or .env; dotenv optional to avoid runtime crash if missing
    try:
        from dotenv import load_dotenv  # type: ignore
        load_dotenv()
    except Exception:
        # Fallback: manually parse .env if present
        try:
            with open(".env", "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    key, val = line.split("=", 1)
                    key = key.strip()
                    val = val.strip().strip('"').strip("'")
                    os.environ.setdefault(key, val)
        except Exception:
            pass

    def getenv_any(keys: list[str], default: str | None = None) -> str | None:
        for k in keys:
            v = os.getenv(k)
            if v is not None and v.strip() != "":
                return v.strip()
        return default

    token = getenv_any(["DISCORD_TOKEN", "TOKEN", "BOT_TOKEN"], "") or ""
    app_id_val = getenv_any(["APP_ID", "APPLICATION_ID", "CLIENT_ID"], "0") or "0"
    owner_id_val = getenv_any(["OWNER_ID", "OWNER", "BOT_OWNER"], "0") or "0"
    guild_id_env = getenv_any(["GUILD_ID", "SERVER_ID", "GUILD"])  # may be empty
    app_id = int(app_id_val) if app_id_val.isdigit() else 0
    owner_id = int(owner_id_val) if owner_id_val.isdigit() else 0
    guild_id = int(guild_id_env) if guild_id_env and guild_id_env.isdigit() else None
    sync_global = (getenv_any(["SYNC_GLOBAL", "GLOBAL_SYNC"], "false") or "false").lower() in {"1", "true", "yes"}
    yt_cookies = os.getenv("YT_COOKIES")
    lavalink_host = os.getenv("LAVALINK_HOST", "127.0.0.1").strip() or "127.0.0.1"
    lavalink_port = int(os.getenv("LAVALINK_PORT", "2333") or 2333)
    lavalink_password = os.getenv("LAVALINK_PASSWORD", "youshallnotpass") or "youshallnotpass"
    
    # Debug logging
    print(f"DEBUG: Loaded Lavalink password: '{lavalink_password}'")

    if not token:
        raise RuntimeError("DISCORD_TOKEN is required. Set in environment or .env (accepted: DISCORD_TOKEN, TOKEN, BOT_TOKEN)")
    if not app_id:
        raise RuntimeError("APP_ID is required. Set in environment or .env (accepted: APP_ID, APPLICATION_ID, CLIENT_ID)")
    if not owner_id:
        raise RuntimeError("OWNER_ID is required. Set in environment or .env (accepted: OWNER_ID, OWNER, BOT_OWNER)")

    return BotConfig(
        token=token,
        app_id=app_id,
        owner_id=owner_id,
        guild_id=guild_id,
        sync_global=sync_global,
        yt_cookies=yt_cookies,
        lavalink_host=lavalink_host,
        lavalink_port=lavalink_port,
        lavalink_password=lavalink_password,
    )
