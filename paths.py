"""Central configuration: paths + secrets from .env

All other modules import from here. Secrets are loaded once at import time.

Layout:
  data/   - CSV logs, JSON state (gets updated as bot runs)
  output/ - generated reports (Excel, backtest CSVs)
  root/   - code, session files (curl.txt), bot.log
"""
import os

ROOT = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(ROOT, "data")
OUTPUT_DIR = os.path.join(ROOT, "output")

# data files (state, accumulated logs)
LOG_FILE        = os.path.join(DATA_DIR, "odds_log.csv")
MATCHES_FILE    = os.path.join(DATA_DIR, "matches.csv")
HISTORICAL_FILE = os.path.join(DATA_DIR, "historical_bets.csv")
AUTO_BETS_FILE  = os.path.join(DATA_DIR, "auto_bets.csv")
BANK_FILE       = os.path.join(DATA_DIR, "bot_bank.json")

# generated outputs
DASHBOARD_FILE        = os.path.join(OUTPUT_DIR, "odds_dashboard.xlsx")
BACKTEST_RESULTS_FILE = os.path.join(OUTPUT_DIR, "backtest_results.csv")
BACKTEST_DETAILS_FILE = os.path.join(OUTPUT_DIR, "backtest_details.csv")

# session / runtime (root)
CURL_FILE = os.path.join(ROOT, "curl.txt")
BOT_LOG   = os.path.join(ROOT, "bot.log")

# debug dumps (root, gitignored)
DEBUG_EVENTS_FILE = os.path.join(ROOT, "debug_events.json")
DEBUG_STAT_FILE   = os.path.join(ROOT, "debug_stat.json")

# transient IPC markers (root, gitignored)
WINNER_NEEDED_FILE = os.path.join(ROOT, "winner_needed.txt")
WINNER_ANSWER_FILE = os.path.join(ROOT, "winner_answer.txt")

# auto-create dirs on import
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)


# ----------- secrets from .env -----------

def _load_env(env_path=os.path.join(ROOT, ".env")):
    """Minimal .env parser. Reads KEY=VALUE lines, ignores #-comments and blanks."""
    if not os.path.exists(env_path):
        return
    with open(env_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            k, _, v = line.partition("=")
            k = k.strip()
            v = v.strip().strip('"').strip("'")
            # don't overwrite real shell env if already set
            os.environ.setdefault(k, v)


_load_env()

TG_ALERT_TOKEN   = os.environ.get("TG_ALERT_TOKEN", "")
TG_CHAT_ID       = os.environ.get("TG_CHAT_ID", "")
TG_CONTROL_TOKEN = os.environ.get("TG_CONTROL_TOKEN", "")
