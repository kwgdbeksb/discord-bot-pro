#!/usr/bin/env bash
set -euo pipefail

# Always operate relative to this script's directory so paths work on any panel
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# Ensure Python can see the project root even if the panel cwd differs
export PYTHONPATH="${SCRIPT_DIR}:${PYTHONPATH:-}"
# Also add common container root for bot-hosting panels
if [[ -d "/home/container" ]]; then
  export PYTHONPATH="/home/container:${PYTHONPATH}"
fi

# Load .env into the process environment so Python sees required secrets
if [[ -f .env ]]; then
  echo "[start.sh] Loading .env into environment..."
  set -a
  . ./.env
  set +a
else
  echo "[start.sh] WARNING: .env not found at ${SCRIPT_DIR}. Ensure panel Variables are set (DISCORD_TOKEN, APP_ID, OWNER_ID)."
fi

# Sanity check without printing secrets
if [[ -z "${DISCORD_TOKEN:-}" ]]; then
  echo "[start.sh] ERROR: DISCORD_TOKEN not found after loading .env/variables."
else
  echo "[start.sh] OK: DISCORD_TOKEN is present."
fi

echo "[start.sh] Installing Python dependencies..."
if [[ -f requirements.txt ]]; then
  pip install --disable-pip-version-check -r requirements.txt
fi

# Bind Lavalink to panel-assigned port
export PORT="${SERVER_PORT:-2333}"
export LAVALINK_HOST="${LAVALINK_HOST:-127.0.0.1}"
export LAVALINK_PORT="${LAVALINK_PORT:-$PORT}"
export LAVALINK_PASSWORD="${LAVALINK_PASSWORD:-youshallnotpass}"

start_local_lavalink=false
JAR_PATH=""
LOG_DIR="$SCRIPT_DIR/lavalink/logs"
if [[ -f "$SCRIPT_DIR/lavalink/Lavalink.jar" ]]; then
  JAR_PATH="$SCRIPT_DIR/lavalink/Lavalink.jar"
elif [[ -f "$SCRIPT_DIR/Lavalink.jar" ]]; then
  # Fallback: allow jar at repo root
  JAR_PATH="$SCRIPT_DIR/Lavalink.jar"
elif [[ -f "$SCRIPT_DIR/lavalink/lavalink.jar" ]]; then
  # Handle lowercase filename variants
  JAR_PATH="$SCRIPT_DIR/lavalink/lavalink.jar"
elif [[ -f "$SCRIPT_DIR/lavalink.jar" ]]; then
  JAR_PATH="$SCRIPT_DIR/lavalink.jar"
fi

if [[ -n "$JAR_PATH" ]]; then
  if command -v java >/dev/null 2>&1; then
    mkdir -p "$LOG_DIR"
    echo "[start.sh] Starting Lavalink on ${LAVALINK_HOST}:${PORT} using $JAR_PATH..."
    nohup java ${JAVA_FLAGS:-} -jar "$JAR_PATH" > "$LOG_DIR/panel-start.log" 2>&1 &
    start_local_lavalink=true
  else
    echo "[start.sh] WARNING: Java not found in image; skipping local Lavalink start."
  fi
else
  echo "[start.sh] WARNING: Lavalink.jar not found (checked ./lavalink/Lavalink.jar, ./lavalink/lavalink.jar, ./Lavalink.jar, ./lavalink.jar); skipping local Lavalink start."
fi

# Optional readiness check (only if we attempted local Lavalink)
if [[ "$start_local_lavalink" == "true" ]]; then
  echo "[start.sh] Waiting for Lavalink to become ready..."
  ready=0
  for i in {1..20}; do
    if command -v curl >/dev/null 2>&1; then
      if curl -s --max-time 2 "http://127.0.0.1:${PORT}/v4/info" >/dev/null; then
        ready=1; break
      fi
    else
      # Fallback: simple delay if curl is unavailable
      sleep 1
    fi
    sleep 0.5
  done
  if [[ $ready -eq 1 ]]; then
    echo "[start.sh] Lavalink is up."
  else
    echo "[start.sh] WARNING: Lavalink readiness not confirmed; proceeding to start bot."
  fi
fi

echo "[start.sh] Starting Discord bot..."
echo "[start.sh] Normalizing project layout (fixing stray 'src\\' filenames)..."
python <<'PY'
import os, shutil
root = os.getcwd()
src = os.path.join(root, 'src')
os.makedirs(src, exist_ok=True)
os.makedirs(os.path.join(src, 'cogs'), exist_ok=True)
os.makedirs(os.path.join(src, 'utils'), exist_ok=True)

moved = 0
# If src/bot.py already exists, we're good; otherwise move any files named like 'src\\...'
if not os.path.isfile(os.path.join(src, 'bot.py')):
    for name in os.listdir(root):
        if '\\' not in name:
            continue
        if not name.startswith('src\\'):
            continue
        parts = name.split('\\')
        dest = os.path.join(root, *parts)
        parent = os.path.dirname(dest)
        try:
            os.makedirs(parent, exist_ok=True)
            src_path = os.path.join(root, name)
            if os.path.exists(src_path) and not os.path.exists(dest):
                shutil.move(src_path, dest)
                moved += 1
        except Exception as e:
            print(f"[start.sh] WARN: could not move {name}: {e}")

print(f"[start.sh] Layout normalization complete. Moved {moved} file(s).")
PY

# Prefer running the real src/bot.py if it exists; otherwise use wrapper
if [[ -f "src/bot.py" ]]; then
  echo "[start.sh] Detected src/bot.py. Launching directly."
  exec python src/bot.py
else
  echo "[start.sh] src/bot.py not found. Launching wrapper bot.py."
  exec python bot.py
fi
