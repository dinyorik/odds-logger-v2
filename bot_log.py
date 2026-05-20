"""Shared logger for bot decisions. Used by odds_logger.py and bet_placer.py.
Writes to bot.log + stdout. Thread-safe."""
import datetime
import threading

from paths import BOT_LOG as LOG_FILE
_lock = threading.Lock()


def log(msg: str) -> None:
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    with _lock:
        try:
            with open(LOG_FILE, "a", encoding="utf-8") as f:
                f.write(line + "\n")
        except OSError:
            pass  # never let logging crash the bot
