"""
Odds logger for melbet (Mobile Legends).

What it does:
  - every INTERVAL seconds pings gameEvents and statistic
  - writes one tick to odds_log.csv
  - on first run saves raw JSON to debug_events.json / debug_stat.json
  - detects map end (via fullScoreDetail change) and auto-records
    a row in matches.csv with: min cf, when window opened <1.3, etc.
  - teams parsed by `type` field (1 = A, 3 = B), NOT by array order.

Before each match change: GAME_ID, MAP_NUM, optionally DOMAIN.
GAME_ID is taken from the gameEvents cURL in DevTools Network -> param gameId.
When mirror changes (domain) -> update DOMAIN, COOKIES, x-hd, referer fully
from the fresh cURL.
"""

import argparse
import csv
import json
import os
import queue
import threading
import time
from datetime import datetime

import requests

# ============================================================
GAME_ID = "334144480"
MAP_NUM = 4
LIVE = True
DOMAIN = "melbet-701203.top"
# ============================================================

BASE = f"https://{DOMAIN}/cyber-api"
FEED = "mainfeedlive" if LIVE else "mainfeedline"

EVENTS_URL = f"{BASE}/{FEED}/web/cyber/v1/gameEvents"
STAT_URL = f"{BASE}/{FEED}/web/cyber/v1/statistic"

HEADERS = {
    "accept": "application/json, text/plain, */*",
    "accept-language": "en-US,en;q=0.9,ru;q=0.8",
    "content-type": "application/json",
    "user-agent": "Mozilla/5.0 (Linux; Android 6.0; Nexus 5 Build/MRA58N) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Mobile Safari/537.36",
    "x-app-n": "__CYBER_APP__",
    "x-mobile-project-id": "0",
    "x-requested-with": "XMLHttpRequest",
    "x-svc-source": "__CYBER_APP__",
    "x-hd": 'KLUzHOSOXCbjaV2JF2W+hO1orqMSSx+Hhm0FSLq1k3uP9cEA2I6SDsE1+/035Sp1cVPTPXJtllUjT3HTQReiv+w/Rt9wsRJeinVQvkNNbs8LcFWnIaw74HM7Hz0F+pscsbctGOb5sh3MNxElp/766elZK9yf+EldonSCbxsF+u0AG8GU8odtOTayy3k7Hng9hZ/TAvUL8AN+9PXHvW8ofb7cbnas+BKTfSxqKIht1M8b0qF2U5zIKuYPHIJKEpwzZEe+2RvNAiORRHv7PSi8S843TRusiXFnVh5WFP4/bqmDdp6bOAfgBnz3jQRch8EuRsEckPRJeURDWd15XMf3uq2FlmJlXHEYQOs6tneypUxyddZj5Y6a7xlXC+UuxNlTDRDrDTcR53VrZeADUXHM7wwH8gZchQWlvlLf2zjDfBSobjxSgnjMwufAENJSJeBMyjYBH2tW/ZZ3GxmB/6NM3luakpF1bvv8YBwk2FJCEpPKynfPBbbSAG1PmtIWWJxXf1RZf2Oq5481MBlfXRPkx0pPENsh1Th1jGo0eKtvWXwoJHtPXgWOTMzXamSKEqpMo7eO4YyEWpW1XuqBXyAaV3BIq4DQNRQYqGFS784aNUliKs31KKAn0txvPmD1DCkXnaqERLs0ZG53qNyRcWh8VNKXMZF2TQ==',
    "dnt": "1",
    "is-srv": "false",
    "referer": 'https://melbet-701203.top/en/esports/real/mobile-legends/2360764-mobile-legends-mpl-malaysia/line/334144480-bigetron-my-by-vit-team-flash',
    "sec-fetch-dest": "empty",
    "sec-fetch-mode": "cors",
    "sec-fetch-site": "same-origin",
}

COOKIES = {
    'fatman_uuid': '8f7eebe5-15c4-f546-0778-a75818157925',
    'application_locale': 'en',
    'sh.session.id': 'd0a209a4-7785-4c97-9963-b152de76a506',
    'coefview': '0',
    '_gcl_au': '1.1.427882445.1776418309',
    '_twpid': 'tw.1776418308793.258594628807217627',
    'uhash': 'd9344faf9298eb24d4b99b230cd00d37',
    'cur': 'KGS',
    'userhash': '37496647f171660929d11a05d7350f16545b39ccf3',
    'che_g': 'ed9182a6-175e-44d1-86ec-e2610b9f5c91',
    '_fbp': 'fb.1.1777951587005.849883136305375571',
    '_ga': 'GA1.1.1142146619.1776418308',
    'che_i': '4',
    'platform_type': 'desktop',
    'tzo': '6',
    'fast_coupon': 'true',
    'v3fr': '1',
    'lng': 'en',
    'cookies_agree_type': '3',
    'is12h': '0',
    'auid': 'sv0ZXWoMiYMlvy8eA25/Ag==',
    'ua': '1538932801',
    'PAY_SESSION': 'a973d8c9a6fe419d1931f0d1edf3be3b',
    'SESSION': '760bdc3952c7c7ebacacf14534d8512d',
    '_ga_435XWQE678': 'GS2.1.s1779206601$o73$g1$t1779206658$j3$l0$h0',
    'user_token': 'eyJhbGciOiJFUzI1NiIsImtpZCI6IjEiLCJ0eXAiOiJKV1QifQ.eyJzdWIiOiI1MC8xNTM4OTMyODAxIiwicGlkIjoiOCIsImp0aSI6IjAvNDYwM2NmZTZlZmY1MGFlZmM1YTA2NjI3NDNkMDcyMTJmYjA1NWFiNTFlYjE0ZmQ0Y2MyMDc3MmZjNzdmMGFmMiIsImFwcCI6Ik5BIiwic2lkIjoiMDE5ZTQwZjktMzhjZC03NzVhLWE4MWYtNmEwYTZiMTNlZGQwIiwiaW5uZXIiOiJ0cnVlIiwic2NvcGUiOiJhbGwiLCJ3dCI6InRydWUiLCJuYmYiOjE3NzkyMDY1MzUsImV4cCI6MTc3OTIyMDkzNSwiaWF0IjoxNzc5MjA2NTM1fQ.VFqe3bX3KUneW9j24vNk6InmsOo3SAM7dOpjctYBws8jdXvMUWgszPEmZQluRoDHnsMsXv7UF40zjhCvIh2iGg',
    '_ga_8SZ536WC7F': 'GS2.1.s1779206601$o72$g1$t1779206661$j60$l1$h647812423',
    'window_width': '1350',
    'hide_right': '0',
}

INTERVAL = 3
from paths import LOG_FILE, MATCHES_FILE, DEBUG_EVENTS_FILE, DEBUG_STAT_FILE, WINNER_NEEDED_FILE, WINNER_ANSWER_FILE
WINDOW_THRESHOLD = 1.30  # threshold for "window detected": cf <= this value

# -- Auto-betting bot --------------------------------------------------
BOT_ENABLED      = True   # False = logging only, no bets
CF_BET_THRESHOLD = 1.20   # place bet if cf < this

try:
    from bet_placer import auto_bet as _bot_place_bet
    _bet_placer_available = True
except ImportError:
    _bet_placer_available = False
    BOT_ENABLED = False
    print('[BOT] bet_placer.py not found - auto-betting disabled')

# Telegram alerts
from paths import TG_ALERT_TOKEN as TELEGRAM_TOKEN
from paths import TG_CHAT_ID as TELEGRAM_CHAT_ID
ALERT_CF_THRESHOLDS = (1.25, 1.15)  # at each of these levels send TG alert
SCORE_JUMP_THRESHOLD = 3  # +N kills in one tick by one team -> alert

LOG_HEADERS = [
    "timestamp", "match_id", "map_id", "map", "minute", "score", "all_periods",
    "cf_team_a", "cf_team_b", "min_cf_so_far", "blocked", "sec_since_start",
]
MATCHES_HEADERS = [
    "match_id", "map", "started_at", "ended_at",
    "winner", "final_score",
    "min_cf_a", "min_cf_a_at",
    "min_cf_b", "min_cf_b_at",
    "max_cf_a", "max_cf_a_at",
    "max_cf_b", "max_cf_b_at",
    "last_open_cf_a", "last_open_cf_b", "last_open_at", "first_closed_at",
    "first_cf_le_threshold_a", "first_cf_le_threshold_a_at",
    "first_cf_le_threshold_b", "first_cf_le_threshold_b_at",
    "first_cf_le_125_a", "first_cf_le_125_a_at",
    "first_cf_le_120_a", "first_cf_le_120_a_at",
    "first_cf_le_115_a", "first_cf_le_115_a_at",
    "first_cf_le_110_a", "first_cf_le_110_a_at",
    "first_cf_le_105_a", "first_cf_le_105_a_at",
    "first_cf_le_125_b", "first_cf_le_125_b_at",
    "first_cf_le_120_b", "first_cf_le_120_b_at",
    "first_cf_le_115_b", "first_cf_le_115_b_at",
    "first_cf_le_110_b", "first_cf_le_110_b_at",
    "first_cf_le_105_b", "first_cf_le_105_b_at",
    "ticks_logged",
]


# ---------------- telegram ----------------

def send_telegram(text):
    """Send to Telegram. Silent on missing token or network error."""
    # (function body follows)
    if not TELEGRAM_TOKEN:
        return
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        requests.post(url, json={
            "chat_id": TELEGRAM_CHAT_ID,
            "text": text,
            "parse_mode": "HTML",
        }, timeout=5)
    except Exception:
        pass


# ---------------- network ----------------

def fetch(session, url, game_id, with_cfview=True):
    """GET with cookies/headers. statistic does not accept cfView."""
    # Param order is preserved manually; server rejects reordered params
    # (InvalidQueryParametersException).
    if with_cfview:
        qs = f"cfView=3&country=82&gameId={game_id}&gr=1517&lng=en&ref=8"
    else:
        qs = f"country=82&gameId={game_id}&gr=1517&lng=en&ref=8"
    full_url = f"{url}?{qs}"
    r = session.get(full_url, headers=HEADERS, cookies=COOKIES, timeout=10)
    if r.status_code in (401, 403):
        raise requests.HTTPError(
            f"AUTH FAILED ({r.status_code}). Session/cookies expired. "
            f"Body: {r.text[:300]}"
        )
    if not r.ok:
        raise requests.HTTPError(f"{r.status_code} {r.reason} | Body: {r.text[:500]}")
    return r.json()


# ---------------- parsers ----------------

def parse_events(data, map_num):
    """Returns (cf_a, cf_b, blocked, map_id, found)."""
    # found=False means our map is no longer in the response -- map ended.
    # Do NOT fall back to main game (it has mixed-up odds after map end).
    # We read fields by `type` (1=A, 3=B), not by array index, since the
    # server can reorder teams between requests.
    target_name = f"{map_num} map"
    source = None
    has_subgames = bool(data.get("subGamesForMainGame"))
    for sub in data.get("subGamesForMainGame", []):
        if sub.get("subGameName") == target_name:
            source = sub
            break
    if source is None:
        if has_subgames:
            # subgames present, but ours not in them -> map ended or not started
            return None, None, None, None, False
        source = data  # no subgames at all -> probably endpoint without map structure

    for group in source.get("eventGroups", []):
        if group.get("groupId") != 1:
            continue
        ev_a = ev_b = None
        for outcome_list in group.get("events", []):
            for ev in outcome_list:
                t = ev.get("type")
                if t == 1 and ev_a is None:
                    ev_a = ev
                elif t == 3 and ev_b is None:
                    ev_b = ev
        if ev_a is None or ev_b is None:
            return None, None, None, source.get("id", GAME_ID), True
        cf_a = ev_a.get("cf")
        cf_b = ev_b.get("cf")
        blocked = bool(ev_a.get("blocked", False) or ev_b.get("blocked", False))
        return cf_a, cf_b, blocked, source.get("id", GAME_ID), True

    return None, None, None, source.get("id", GAME_ID), True


def parse_stat(data, map_num):
    out = {
        "score_str": None,
        "timer_str": "00:00",
        "running": False,
        "current_period": data.get("currentPeriod"),
        "status": data.get("statusLineStr"),
        "full_score_a": None,
        "full_score_b": None,
        "all_periods": None,  # all maps as a string: "15-19,16-8,16-16,0-0"
    }

    fsd = data.get("fullScoreDetail") or {}
    out["full_score_a"] = fsd.get("scoreOpp1")
    out["full_score_b"] = fsd.get("scoreOpp2")
    out["all_periods"] = data.get("periodScoresStr")

    # 1. try scoreOpp1/2 from current period first
    periods = data.get("periodScores") or []
    current = next((p for p in periods if p.get("period") == map_num), None)
    if current is not None:
        s1 = current.get("scoreOpp1")
        s2 = current.get("scoreOpp2")
        if s1 is not None and s2 is not None:
            out["score_str"] = f"{s1}-{s2}"

    # 2. fallback: for ended/not-yet-started maps scoreOpp1/2 may be missing,
    #    but periodScoresStr is almost always present (e.g. "15-19,16-8,16-16,0-0")
    if out["score_str"] is None and out["all_periods"]:
        parts = out["all_periods"].split(",")
        idx = map_num - 1
        if 0 <= idx < len(parts) and "-" in parts[idx]:
            out["score_str"] = parts[idx].strip()

    timer = data.get("timer") or {}
    sec = timer.get("timeSec", 0) or 0
    out["timer_str"] = f"{sec // 60:02d}:{sec % 60:02d}"
    out["running"] = bool(timer.get("timeRun", False))

    return out


# ---------------- summary tracking ----------------

class MatchTracker:
    def __init__(self, match_id, map_num):
        self.match_id = match_id
        self.map = map_num
        self.started_at = None
        self.ended_at = None
        self.ticks = 0

        self.min_cf_a = None
        self.min_cf_a_at = None
        self.min_cf_b = None
        self.min_cf_b_at = None
        self.max_cf_a = None
        self.max_cf_a_at = None
        self.max_cf_b = None
        self.max_cf_b_at = None

        # last cf before market closed
        self.last_open_cf_a = None
        self.last_open_cf_b = None
        self.last_open_at = None
        self.first_closed_at = None

        self.first_le_a = None
        self.first_le_a_at = None
        self.first_le_b = None
        self.first_le_b_at = None

        # for each threshold -- moment when cf first dropped below it on OPEN
        self.first_le_thr_a = {}  # {"125": (cf, ts), ...}
        self.first_le_thr_b = {}
        self.thresholds = (1.25, 1.20, 1.15, 1.10, 1.05)


        self.initial_full_score = None
        self.last_full_score = None
        self.winner = None
        self.final_score_str = None

        # telegram-alert dedup: key ("A"/"B", threshold)
        self.alerts_sent = set()
        self.last_score_a = None
        self.last_score_b = None

    def update(self, ts, cf_a, cf_b, blocked, full_score_a, full_score_b, score_str):
        self.ticks += 1
        if self.started_at is None:
            self.started_at = ts
        self.ended_at = ts

        # save last cf at OPEN tick
        if cf_a is not None and cf_b is not None:
            if not blocked:
                self.last_open_cf_a = cf_a
                self.last_open_cf_b = cf_b
                self.last_open_at = ts
            elif self.first_closed_at is None and self.last_open_at is not None:
                # first transition open -> closed
                self.first_closed_at = ts

        if cf_a is not None:
            if self.min_cf_a is None or cf_a < self.min_cf_a:
                self.min_cf_a = cf_a
                self.min_cf_a_at = ts
            if self.max_cf_a is None or cf_a > self.max_cf_a:
                self.max_cf_a = cf_a
                self.max_cf_a_at = ts
            if cf_a <= WINDOW_THRESHOLD and self.first_le_a is None:
                self.first_le_a = cf_a
                self.first_le_a_at = ts
            if not blocked:
                for thr in self.thresholds:
                    key = f"{round(thr * 100)}"
                    if cf_a <= thr and key not in self.first_le_thr_a:
                        self.first_le_thr_a[key] = (cf_a, ts)

        if cf_b is not None:
            if self.min_cf_b is None or cf_b < self.min_cf_b:
                self.min_cf_b = cf_b
                self.min_cf_b_at = ts
            if self.max_cf_b is None or cf_b > self.max_cf_b:
                self.max_cf_b = cf_b
                self.max_cf_b_at = ts
            if cf_b <= WINDOW_THRESHOLD and self.first_le_b is None:
                self.first_le_b = cf_b
                self.first_le_b_at = ts
            if not blocked:
                for thr in self.thresholds:
                    key = f"{round(thr * 100)}"
                    if cf_b <= thr and key not in self.first_le_thr_b:
                        self.first_le_thr_b[key] = (cf_b, ts)

        if score_str:
            self.final_score_str = score_str

        if full_score_a is not None and full_score_b is not None:
            cur = (full_score_a, full_score_b)
            if self.initial_full_score is None:
                self.initial_full_score = cur
            self.last_full_score = cur
            if self.winner is None and self.initial_full_score is not None:
                d_a = cur[0] - self.initial_full_score[0]
                d_b = cur[1] - self.initial_full_score[1]
                if d_a > d_b and d_a > 0:
                    self.winner = "A"
                elif d_b > d_a and d_b > 0:
                    self.winner = "B"

    def to_row(self):
        return [
            self.match_id, self.map, self.started_at, self.ended_at,
            self.winner or "", self.final_score_str or "",
            self.min_cf_a if self.min_cf_a is not None else "",
            self.min_cf_a_at or "",
            self.min_cf_b if self.min_cf_b is not None else "",
            self.min_cf_b_at or "",
            self.max_cf_a if self.max_cf_a is not None else "",
            self.max_cf_a_at or "",
            self.max_cf_b if self.max_cf_b is not None else "",
            self.max_cf_b_at or "",
            self.last_open_cf_a if self.last_open_cf_a is not None else "",
            self.last_open_cf_b if self.last_open_cf_b is not None else "",
            self.last_open_at or "",
            self.first_closed_at or "",
            self.first_le_a if self.first_le_a is not None else "",
            self.first_le_a_at or "",
            self.first_le_b if self.first_le_b is not None else "",
            self.first_le_b_at or "",
            self.first_le_thr_a.get("125", ("", ""))[0],
            self.first_le_thr_a.get("125", ("", ""))[1],
            self.first_le_thr_a.get("120", ("", ""))[0],
            self.first_le_thr_a.get("120", ("", ""))[1],
            self.first_le_thr_a.get("115", ("", ""))[0],
            self.first_le_thr_a.get("115", ("", ""))[1],
            self.first_le_thr_a.get("110", ("", ""))[0],
            self.first_le_thr_a.get("110", ("", ""))[1],
            self.first_le_thr_a.get("105", ("", ""))[0],
            self.first_le_thr_a.get("105", ("", ""))[1],
            self.first_le_thr_b.get("125", ("", ""))[0],
            self.first_le_thr_b.get("125", ("", ""))[1],
            self.first_le_thr_b.get("120", ("", ""))[0],
            self.first_le_thr_b.get("120", ("", ""))[1],
            self.first_le_thr_b.get("115", ("", ""))[0],
            self.first_le_thr_b.get("115", ("", ""))[1],
            self.first_le_thr_b.get("110", ("", ""))[0],
            self.first_le_thr_b.get("110", ("", ""))[1],
            self.first_le_thr_b.get("105", ("", ""))[0],
            self.first_le_thr_b.get("105", ("", ""))[1],
            self.ticks,
        ]

    def print_summary(self):
        print()
        print("=" * 60)
        print(f"SUMMARY: match {self.match_id} map {self.map}")
        print("=" * 60)
        print(f"  ticks recorded:   {self.ticks}")
        print(f"  started:          {self.started_at}")
        print(f"  ended:            {self.ended_at}")
        print(f"  winner:           {self.winner or '-- (not detected)'}")
        print(f"  final score:      {self.final_score_str or '--'}")
        print(f"  min cf A:         {self.min_cf_a} at {self.min_cf_a_at}")
        print(f"  max cf A:         {self.max_cf_a} at {self.max_cf_a_at}")
        print(f"  min cf B:         {self.min_cf_b} at {self.min_cf_b_at}")
        print(f"  max cf B:         {self.max_cf_b} at {self.max_cf_b_at}")
        if self.last_open_at and self.first_closed_at:
            print(f"  last cf before close: A={self.last_open_cf_a} B={self.last_open_cf_b} at {self.last_open_at}")
            print(f"  market closed at: {self.first_closed_at}")
        if self.first_le_a_at:
            print(f"  A first time <={WINDOW_THRESHOLD}: {self.first_le_a} at {self.first_le_a_at}")
        if self.first_le_b_at:
            print(f"  B first time <={WINDOW_THRESHOLD}: {self.first_le_b} at {self.first_le_b_at}")
        if self.winner and self.first_le_a_at and self.first_le_b_at is None and self.winner == "A":
            print(f"  -> bet on A in window WAS WIN")
        if self.winner and self.first_le_b_at and self.first_le_a_at is None and self.winner == "B":
            print(f"  -> bet on B in window WAS WIN")
        print("=" * 60)


# ---------------- main ----------------

def append_match_summary(tracker):
    new = not os.path.exists(MATCHES_FILE)
    with open(MATCHES_FILE, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if new:
            w.writerow(MATCHES_HEADERS)
        w.writerow(tracker.to_row())


def main():
    global BOT_ENABLED
    global GAME_ID, MAP_NUM

    # CLI args: can be passed as flags, otherwise defaults to file values
    ap = argparse.ArgumentParser()
    ap.add_argument("--game-id", type=str, default=GAME_ID,
                    help="match ID (overrides GAME_ID constant)")
    ap.add_argument("--map", type=int, default=MAP_NUM,
                    help="map number (overrides MAP_NUM constant)")
    ap.add_argument("--start-min", type=int, default=None,
                    help="(disabled) seconds offset of match minute at stream start. None = no timer")
    args = ap.parse_args()

    GAME_ID = args.game_id
    MAP_NUM = args.map
    match_offset_sec = args.start_min

    session = requests.Session()
    tracker = MatchTracker(GAME_ID, MAP_NUM)
    bet_placed_maps = set()  # map_ids where bot already placed a bet

    if match_offset_sec is None:
        print()
        print(f"Game {GAME_ID}, map {MAP_NUM}. Timer disabled.")
        print()
    else:
        mm, ss = divmod(match_offset_sec, 60)
        print()
    print()

    # write header if file is new OR empty OR first line is not header-like
    log_needs_header = True
    if os.path.exists(LOG_FILE) and os.path.getsize(LOG_FILE) > 0:
        with open(LOG_FILE, "r", encoding="utf-8") as _f:
            first = _f.readline().strip()
        if first.startswith("timestamp,"):
            log_needs_header = False

    # Token pre-flight check
    if BOT_ENABLED:
        try:
            from token_helper import get_token_seconds_left, format_state
            _secs, _err = get_token_seconds_left()
            _state = format_state(_secs, _err)
            if _err or _secs is None or _secs <= 0:
                print("=" * 60)
                print("!!! " + _state)
                print("!!! Bot DISABLED for this run. Logger keeps working.")
                print("!!! Refresh curl.txt + run update_session.py, then restart.")
                print("=" * 60)
                send_telegram("<b>BOT DISABLED</b>\n" + _state + "\nRefresh curl.txt to resume betting.")
                BOT_ENABLED = False
            elif _secs < 1800:
                print("!!! WARNING: " + _state)
                send_telegram("<b>Token warning</b>\n" + _state)
            else:
                print("[OK] " + _state)
        except Exception as _e:
            print("[WARN] token check crashed: " + str(_e))

    print(f"Match: {GAME_ID} | Map: {MAP_NUM} | Domain: {DOMAIN} | LIVE={LIVE}")
    print(f"Log: {LOG_FILE}  |  Summary: {MATCHES_FILE}")
    print("Ctrl+C to stop -- summary per match written automatically.\n")

    consecutive_errors = 0
    debug_dumped = False

    try:
        with open(LOG_FILE, "a", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            if log_needs_header:
                writer.writerow(LOG_HEADERS)

            while True:
                try:
                    events_data = fetch(session, EVENTS_URL, GAME_ID, with_cfview=True)
                    stat_data = fetch(session, STAT_URL, GAME_ID, with_cfview=False)
                    consecutive_errors = 0
                except requests.HTTPError as e:
                    print(f"[{datetime.now():%H:%M:%S}] {e}")
                    consecutive_errors += 1
                    if consecutive_errors >= 5:
                        print("5 errors in a row. Stopping -- update session and restart.")
                        break
                    time.sleep(INTERVAL)
                    continue
                except requests.RequestException as e:
                    print(f"[{datetime.now():%H:%M:%S}] Network error: {e}")
                    consecutive_errors += 1
                    if consecutive_errors >= 10:
                        print("10 network errors in a row. Stopping.")
                        break
                    time.sleep(INTERVAL)
                    continue

                if not debug_dumped:
                    with open(DEBUG_EVENTS_FILE, "w", encoding="utf-8") as df:
                        json.dump(events_data, df, ensure_ascii=False, indent=2)
                    with open(DEBUG_STAT_FILE, "w", encoding="utf-8") as df:
                        json.dump(stat_data, df, ensure_ascii=False, indent=2)
                    debug_dumped = True

                cf_a, cf_b, blocked, map_id, found = parse_events(events_data, MAP_NUM)
                stat = parse_stat(stat_data, MAP_NUM)

                # map ended: subgame with our MAP_NUM no longer in response
                if not found:
                    print(f"\n>>> Map {MAP_NUM} disappeared from response -- map ended. Auto-stop.\n")
                    send_telegram(f"🛑[STOP] Map {MAP_NUM} ended (match {GAME_ID})")
                    break

                # extra detector: currentPeriod moved forward
                cur_p = stat.get("current_period")
                if cur_p is not None and cur_p > MAP_NUM:
                    print(f"\n>>> currentPeriod={cur_p}, map {MAP_NUM} ended. Auto-stop.\n")
                    send_telegram(f"🛑[STOP] Map {MAP_NUM} ended (match {GAME_ID})")
                    break

                if cf_a is None or cf_b is None:
                    print(f"[{datetime.now():%H:%M:%S}] no cf for map {MAP_NUM} -- "
                          f"check debug_events.json")
                    time.sleep(INTERVAL)
                    continue

                ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                tracker.update(
                    ts, cf_a, cf_b, blocked,
                    stat["full_score_a"], stat["full_score_b"],
                    stat["score_str"],
                )


                # -- BOT SIGNAL (kill_aware_0 filter) -------------------
                if BOT_ENABLED and not blocked:
                    import threading
                    _sa = _sb = None
                    if stat["score_str"] and "-" in stat["score_str"]:
                        try:
                            _sa, _sb = (int(x) for x in stat["score_str"].split("-"))
                        except (ValueError, TypeError):
                            pass
                    for _team_type, _cf in ((1, cf_a), (3, cf_b)):
                        if _cf >= CF_BET_THRESHOLD or map_id in bet_placed_maps:
                            continue
                        _team_lbl = 'A' if _team_type == 1 else 'B'
                        if _sa is not None:
                            _kdiff = (_sa - _sb) if _team_type == 1 else (_sb - _sa)
                            if _kdiff < 0:
                                from bot_log import log as _bot_log
                                _bot_log(f'[BOT] Skip {_team_lbl}: cf={_cf:.3f} killdiff={_kdiff} (score {_sa}-{_sb})')
                                continue
                        bet_placed_maps.add(map_id)
                        from bot_log import log as _bot_log
                        _bot_log(f'[BOT] Signal on team {_team_lbl} cf={_cf:.3f}')
                        threading.Thread(
                            target=_bot_place_bet,
                            args=(int(map_id), str(MAP_NUM), _team_type, _cf),
                            daemon=True,
                        ).start()
                        break
                min_so_far = min(
                    tracker.min_cf_a if tracker.min_cf_a is not None else 999,
                    tracker.min_cf_b if tracker.min_cf_b is not None else 999,
                )
                # match minute: offset from broadcast + time since script start
                if tracker.started_at:
                    from datetime import datetime as _dt
                    try:
                        delta = int((_dt.strptime(ts, "%Y-%m-%d %H:%M:%S")
                                     - _dt.strptime(tracker.started_at, "%Y-%m-%d %H:%M:%S")).total_seconds())
                    except Exception:
                        delta = 0
                else:
                    delta = 0
                if match_offset_sec is not None:
                    total_sec = match_offset_sec + delta
                    mm, ss = divmod(total_sec, 60)
                    sec_since = total_sec
                else:
                    match_minute = ""
                    sec_since = delta

                writer.writerow([
                    ts, GAME_ID, map_id, MAP_NUM,
                    match_minute or stat["timer_str"],
                    stat["score_str"] or "?-?",
                    stat["all_periods"] or "",
                    cf_a, cf_b,
                    min_so_far if min_so_far != 999 else "",
                    blocked,
                    sec_since,
                ])
                f.flush()

                arrow = "A <<<" if cf_a < cf_b else "B <<<"
                blocked_icon = "[X]CLOSED" if blocked else "[V]OPEN  "
                score_disp = stat["score_str"] or "?-?"
                shown_min = match_minute or stat["timer_str"]
                min_prefix = "[T]" if match_minute else "[~]"
                print(f"{ts} | {min_prefix}{shown_min} | {score_disp:<8} | "
                      f"A:{cf_a:<6} B:{cf_b:<6} | {arrow} | {blocked_icon}")

                # ---------- TELEGRAM ALERTS ----------
                if not blocked:
                    for thr in ALERT_CF_THRESHOLDS:
                        if cf_a <= thr and ("A", thr) not in tracker.alerts_sent:
                            tracker.alerts_sent.add(("A", thr))
                            send_telegram(
                                f"<b>⚡️ A broke {thr}</b>\n"
                                f"Live: A={cf_a} B={cf_b}\n"
                                f"Score: {score_disp} | min {shown_min}\n"
                                f"Match {GAME_ID} map {MAP_NUM}"
                            )
                        if cf_b <= thr and ("B", thr) not in tracker.alerts_sent:
                            tracker.alerts_sent.add(("B", thr))
                            send_telegram(
                                f"<b>⚡️ B broke {thr}</b>\n"
                                f"Live: A={cf_a} B={cf_b}\n"
                                f"Score: {score_disp} | min {shown_min}\n"
                                f"Match {GAME_ID} map {MAP_NUM}"
                            )
                if stat["score_str"] and "-" in stat["score_str"]:
                    try:
                        sa, sb = stat["score_str"].split("-")
                        sa, sb = int(sa), int(sb)
                        if tracker.last_score_a is not None:
                            d_a = sa - tracker.last_score_a
                            d_b = sb - tracker.last_score_b
                            if d_a >= SCORE_JUMP_THRESHOLD:
                                send_telegram(
                                    f"<b>⚡️ A: +{d_a} kills</b>\n"
                                    f"{tracker.last_score_a}-{tracker.last_score_b} -> {sa}-{sb}\n"
                                    f"Cf: A={cf_a} B={cf_b} | min {shown_min}"
                                )
                            if d_b >= SCORE_JUMP_THRESHOLD:
                                send_telegram(
                                    f"<b>⚡️ B: +{d_b} kills</b>\n"
                                    f"{tracker.last_score_a}-{tracker.last_score_b} -> {sa}-{sb}\n"
                                    f"Cf: A={cf_a} B={cf_b} | min {shown_min}"
                                )
                        tracker.last_score_a = sa
                        tracker.last_score_b = sb
                    except (ValueError, TypeError):
                        pass

                time.sleep(INTERVAL)

    except KeyboardInterrupt:
        print("\nStopped by user.")
    finally:
        if tracker.ticks > 0:
            # auto-detect winner: lowest final cf AND highest kills must agree
            if tracker.winner is None:
                _ca = tracker.last_open_cf_a
                _cb = tracker.last_open_cf_b
                _sa = tracker.last_score_a
                _sb = tracker.last_score_b
                if (_ca is not None and _cb is not None
                        and _sa is not None and _sb is not None and _ca != _cb and _sa != _sb):
                    cf_winner = "A" if _ca < _cb else "B"
                    kill_winner = "A" if _sa > _sb else "B"
                    if cf_winner == kill_winner:
                        tracker.winner = cf_winner
                        print(f"[AUTO] winner={cf_winner} (cf {_ca} vs {_cb}, score {_sa}-{_sb})")
            tracker.print_summary()
            if tracker.winner is None:
                print()
                print("Winner not auto-detected. Waiting 5 minutes for input.")
                print("Type in console (A/B/skip) or drop winner_answer.txt into the folder.")

                work_dir = os.path.dirname(os.path.abspath(__file__))
                needed_path = WINNER_NEEDED_FILE
                answer_path = WINNER_ANSWER_FILE

                # marker for bot: which match/map we are waiting on
                try:
                    with open(needed_path, "w", encoding="utf-8") as f:
                        f.write(f"{GAME_ID}_{MAP_NUM}")
                except Exception as e:
                    print(f"Could not write {needed_path}: {e}")

                # background thread to read console -- input() blocks
                console_q = queue.Queue()

                def _console_reader():
                    try:
                        line = input("Who won? [A / B / skip] > ")
                        console_q.put(line)
                    except (EOFError, OSError):
                        pass

                t = threading.Thread(target=_console_reader, daemon=True)
                t.start()

                # send TG alert that we need an answer
                try:
                    send_telegram(
                        f"<b>Need winner</b>\n"
                        f"Match {GAME_ID} map {MAP_NUM}\n"
                        f"Final score: {tracker.final_score_str or '?'}\n"
                        f"Reply via bot (/win A or /win B or /win skip)"
                    )
                except Exception:
                    pass

                # poll loop: 5 minutes with 2-sec step
                ans = None
                deadline = time.time() + 300
                while time.time() < deadline:
                    # 1. console?
                    try:
                        ans = console_q.get(timeout=2).strip().upper()
                        break
                    except queue.Empty:
                        pass
                    # 2. file?
                    if os.path.exists(answer_path):
                        try:
                            with open(answer_path, "r", encoding="utf-8") as f:
                                ans = f.read().strip().upper()
                            break
                        except Exception:
                            pass

                if ans is None:
                    print("Timeout 5 minutes. Winner left empty.")
                elif ans in ("A", "B"):
                    tracker.winner = ans
                    print(f"Winner recorded: {ans}")
                elif ans in ("SKIP", "S", ""):
                    print("Winner left empty (skip).")
                else:
                    print(f"Did not understand answer '{ans}'. Winner left empty.")

                # cleanup marker files
                for p in (needed_path, answer_path):
                    try:
                        if os.path.exists(p):
                            os.remove(p)
                    except Exception:
                        pass

            append_match_summary(tracker)
            print(f"Summary appended to {MATCHES_FILE}.")


if __name__ == "__main__":
    main()
