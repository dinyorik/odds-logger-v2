import os
import telebot
import subprocess
import requests
import re
import datetime
import threading
import time
from telebot.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton

from paths import TG_CONTROL_TOKEN as TOKEN
ALLOWED_ID = CHAT_ID  # only this user can control the bot
from paths import TG_CHAT_ID; CHAT_ID = int(TG_CHAT_ID) if TG_CHAT_ID else 0
LOGGER_PATH = r"D:\it\odds-logger-v2\odds_logger.py"
PYTHON_PATH = r"C:\Users\User\AppData\Local\Programs\Python\Python314\python.exe"
from paths import CURL_FILE as CURL_PATH
from paths import ROOT as WORK_DIR, WINNER_NEEDED_FILE, WINNER_ANSWER_FILE

bot = telebot.TeleBot(TOKEN)
proc = None
auto_mode = False

session = {
    "domain": "melbet-701203.top",
    "cookies": {},
    "x_hd": "",
}

# Pending schedule state: {chat_id: (game_id, map_num)}
pending_schedule = {}

# --- Keyboard ---
def main_keyboard():
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    auto_label = "Auto: ON" if auto_mode else "Auto: OFF"
    kb.row(KeyboardButton("Find match"), KeyboardButton("Status"))
    kb.row(KeyboardButton("Stop"), KeyboardButton(auto_label))
    kb.row(KeyboardButton("Update session"))
    return kb

# --- Session ---
def load_session():
    try:
        with open(CURL_PATH, "r", encoding="utf-8-sig") as f:
            curl = f.read()
        m = re.search(r"https?://([^/]+)/", curl)
        if m:
            session["domain"] = m.group(1)
        m = re.search(r"-H\s+['\"]x-hd:\s*(.+?)['\"]", curl)
        if m:
            session["x_hd"] = m.group(1)
        m = re.search(r"-b\s+['\"](.+?)['\"]", curl, re.DOTALL)
        if m:
            session["cookies"] = {}
            for part in m.group(1).split(";"):
                part = part.strip()
                if "=" in part:
                    k, v = part.split("=", 1)
                    session["cookies"][k.strip()] = v.strip()
        return True
    except Exception as e:
        return str(e)

def find_games():
    url = f"https://{session['domain']}/cyber-api/mainfeedlive/web/cyber/v1/gamesBySport/real"
    qs = "cfView=3&country=215&gr=1439&lng=en&ref=8&subSport=36"
    headers = {
        "accept": "application/json, text/plain, */*",
        "x-hd": session["x_hd"],
        "x-app-n": "__CYBER_APP__",
        "x-requested-with": "XMLHttpRequest",
        "x-svc-source": "__CYBER_APP__",
        "referer": f"https://{session['domain']}/en/esports/real/mobile-legends",
        "user-agent": "Mozilla/5.0 (Linux; Android 6.0; Nexus 5 Build/MRA58N) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Mobile Safari/537.36",
    }
    r = requests.get(f"{url}?{qs}", headers=headers, cookies=session["cookies"], timeout=10)
    r.raise_for_status()
    data = r.json()
    games = data.get("games", []) if isinstance(data, dict) else data
    return [g for g in games if "Epic Clash" in g.get("liga", {}).get("name", "")]

def auth_check(msg):
    return msg.from_user.id == ALLOWED_ID

def do_run(game_id, map_num, chat_id):
    global proc
    if proc and proc.poll() is None:
        bot.send_message(chat_id, "Logger already running. Stop first.", reply_markup=main_keyboard())
        return
    try:
        proc = subprocess.Popen(
            [PYTHON_PATH, LOGGER_PATH, "--game-id", str(game_id), "--map", str(map_num)],
            creationflags=subprocess.CREATE_NEW_CONSOLE
        )
        bot.send_message(chat_id, f"Started. PID {proc.pid}\ngame_id={game_id} map={map_num}", reply_markup=main_keyboard())
    except Exception as e:
        bot.send_message(chat_id, f"Launch error: {e}", reply_markup=main_keyboard())

def do_schedule(game_id, map_num, time_str, chat_id):
    try:
        h, m = map(int, time_str.strip().split(":"))
        now = datetime.datetime.now()
        target = now.replace(hour=h, minute=m, second=0, microsecond=0)
        if target <= now:
            target += datetime.timedelta(days=1)
        delay = (target - now).total_seconds()

        def delayed_run():
            time.sleep(delay)
            do_run(game_id, map_num, CHAT_ID)

        threading.Thread(target=delayed_run, daemon=True).start()
        bot.send_message(chat_id, f"Scheduled at {time_str}\ngame_id={game_id} map={map_num}", reply_markup=main_keyboard())
    except Exception as e:
        bot.send_message(chat_id, f"Invalid time format. Use HH:MM\nError: {e}", reply_markup=main_keyboard())

# --- Keyboard button handlers ---
@bot.message_handler(func=lambda m: m.text == "Find match")
def btn_find(msg):
    if not auth_check(msg): return
    cmd_find(msg)

@bot.message_handler(func=lambda m: m.text == "Status")
def btn_status(msg):
    if not auth_check(msg): return
    cmd_status(msg)

@bot.message_handler(func=lambda m: m.text == "Stop")
def btn_stop(msg):
    if not auth_check(msg): return
    cmd_stop(msg)

@bot.message_handler(func=lambda m: m.text == "Update session")
def btn_update(msg):
    if not auth_check(msg): return
    cmd_update(msg)

@bot.message_handler(func=lambda m: m.text in ("Auto: ON", "Auto: OFF"))
def btn_auto(msg):
    if not auth_check(msg): return
    global auto_mode
    auto_mode = not auto_mode
    state = "ON" if auto_mode else "OFF"
    bot.send_message(msg.chat.id, f"Auto mode: {state}", reply_markup=main_keyboard())
# --- Inline callbacks ---
@bot.callback_query_handler(func=lambda call: call.data.startswith("run:"))
def cb_run(call):
    if call.from_user.id != ALLOWED_ID: return
    _, game_id, map_num = call.data.split(":")
    bot.answer_callback_query(call.id)
    do_run(game_id, map_num, call.message.chat.id)

@bot.callback_query_handler(func=lambda call: call.data.startswith("sched:"))
def cb_schedule(call):
    if call.from_user.id != ALLOWED_ID: return
    _, game_id, map_num = call.data.split(":")
    bot.answer_callback_query(call.id)
    pending_schedule[call.message.chat.id] = (game_id, map_num)
    bot.send_message(call.message.chat.id, f"Enter time (HH:MM) to schedule map {map_num}:")

@bot.callback_query_handler(func=lambda call: call.data.startswith("win:"))
def cb_win(call):
    if call.from_user.id != ALLOWED_ID: return
    ans = call.data.split(":")[1].upper()
    answer_path = WINNER_ANSWER_FILE
    try:
        with open(answer_path, "w", encoding="utf-8") as f:
            f.write(ans)
        bot.answer_callback_query(call.id, f"Saved: {ans}")
        bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=None)
        bot.send_message(CHAT_ID, f"Winner saved: {ans}", reply_markup=main_keyboard())
    except Exception as e:
        bot.answer_callback_query(call.id, f"Error: {e}")

# --- Text input handler (for schedule time) ---
@bot.message_handler(func=lambda m: m.chat.id in pending_schedule and re.match(r"^\d{1,2}:\d{2}$", m.text.strip()))
def handle_schedule_time(msg):
    if not auth_check(msg): return
    game_id, map_num = pending_schedule.pop(msg.chat.id)
    do_schedule(game_id, map_num, msg.text.strip(), msg.chat.id)

# --- Commands ---
@bot.message_handler(commands=["start", "help"])
def cmd_help(msg):
    if not auth_check(msg): return
    bot.send_message(msg.chat.id,
        "MLBB Odds Logger Bot\n\n"
        "Buttons: Find match / Status / Stop / Update session\n"
        "/run <game_id> <map>\n"
        "/win A|B|skip",
        reply_markup=main_keyboard()
    )

@bot.message_handler(commands=["update"])
def cmd_update(msg):
    if not auth_check(msg): return
    result = load_session()
    if result is True:
        bot.send_message(msg.chat.id, f"Session updated. Domain: {session['domain']}", reply_markup=main_keyboard())
    else:
        bot.send_message(msg.chat.id, f"Error: {result}", reply_markup=main_keyboard())

@bot.message_handler(commands=["find"])
def cmd_find(msg):
    if not auth_check(msg): return
    try:
        games = find_games()
        if not games:
            bot.send_message(msg.chat.id, "No active MLBB matches", reply_markup=main_keyboard())
            return
        for g in games:
            gid = g.get("id")
            scores = g.get("scores", {})
            map_num = scores.get("currentPeriod", 1)
            t1 = g.get("opponent1", {}).get("fullName", "?")
            t2 = g.get("opponent2", {}).get("fullName", "?")
            match_score = scores.get("fullScore", "0-0")  # maps won e.g. "1-1"
            liga = g.get("liga", {}).get("name", "")

            # Kill score for current map from periodScores
            period_scores = scores.get("periodScores", [])
            kill_score = "?-?"
            for p in period_scores:
                if p.get("period") == map_num:
                    kill_score = f"{p.get('scoreOpp1', '?')}-{p.get('scoreOpp2', '?')}"
                    break

            text = (
                f"{liga}\n"
                f"{t1} vs {t2}\n"
                f"Match: {match_score} | Map {map_num} | Kills: {kill_score}\n"
                f"ID: {gid}"
            )

            inline = InlineKeyboardMarkup()
            inline.row(
                InlineKeyboardButton(f"Run Map {map_num}", callback_data=f"run:{gid}:{map_num}"),
                InlineKeyboardButton("Schedule", callback_data=f"sched:{gid}:{map_num}"),
            )
            bot.send_message(msg.chat.id, text, reply_markup=inline)
    except Exception as e:
        bot.send_message(msg.chat.id, f"Error: {e}", reply_markup=main_keyboard())

@bot.message_handler(commands=["run"])
def cmd_run(msg):
    if not auth_check(msg): return
    parts = msg.text.split()
    if len(parts) < 3:
        bot.send_message(msg.chat.id, "Usage: /run <game_id> <map>", reply_markup=main_keyboard())
        return
    do_run(parts[1], parts[2], msg.chat.id)

@bot.message_handler(commands=["stop"])
def cmd_stop(msg):
    if not auth_check(msg): return
    global proc
    if proc and proc.poll() is None:
        proc.terminate()
        bot.send_message(msg.chat.id, "Logger stopped.", reply_markup=main_keyboard())
    else:
        bot.send_message(msg.chat.id, "Logger not running.", reply_markup=main_keyboard())

@bot.message_handler(commands=["status"])
def cmd_status(msg):
    if not auth_check(msg): return
    global proc
    if proc and proc.poll() is None:
        bot.send_message(msg.chat.id, f"Logger running. PID {proc.pid}", reply_markup=main_keyboard())
    else:
        bot.send_message(msg.chat.id, "Logger not running.", reply_markup=main_keyboard())

@bot.message_handler(commands=["win"])
def cmd_win(msg):
    if not auth_check(msg): return
    parts = msg.text.split()
    if len(parts) < 2:
        bot.send_message(msg.chat.id, "Usage: /win A|B|skip", reply_markup=main_keyboard())
        return
    ans = parts[1].upper()
    answer_path = WINNER_ANSWER_FILE
    try:
        with open(answer_path, "w", encoding="utf-8") as f:
            f.write(ans)
        bot.send_message(msg.chat.id, f"Winner saved: {ans}", reply_markup=main_keyboard())
    except Exception as e:
        bot.send_message(msg.chat.id, f"Error: {e}", reply_markup=main_keyboard())

# --- Winner needed monitor ---
def watch_winner_needed():
    needed_path = WINNER_NEEDED_FILE
    notified = None
    while True:
        try:
            if os.path.exists(needed_path):
                with open(needed_path, "r", encoding="utf-8") as f:
                    content = f.read().strip()
                if content and content != notified:
                    notified = content
                    parts = content.rsplit("_", 1)
                    game_id = parts[0] if len(parts) == 2 else content
                    map_num = parts[1] if len(parts) == 2 else "?"
                    inline = InlineKeyboardMarkup()
                    inline.row(
                        InlineKeyboardButton("A", callback_data="win:A"),
                        InlineKeyboardButton("B", callback_data="win:B"),
                        InlineKeyboardButton("Skip", callback_data="win:SKIP"),
                    )
                    bot.send_message(
                        CHAT_ID,
                        f"Who won?\nMatch {game_id} map {map_num}",
                        reply_markup=inline
                    )
            else:
                notified = None
        except Exception:
            pass
        time.sleep(3)

# --- Auto monitor ---
def auto_monitor():
    while True:
        time.sleep(60)
        if not auto_mode:
            continue
        global proc
        if proc and proc.poll() is None:
            continue
        try:
            games = find_games()
            for g in games:
                scores = g.get("scores", {})
                map_num = scores.get("currentPeriod", 1)
                period_scores = scores.get("periodScores", [])
                kill_a, kill_b = 0, 0
                for p in period_scores:
                    if p.get("period") == map_num:
                        kill_a = p.get("scoreOpp1", 0)
                        kill_b = p.get("scoreOpp2", 0)
                        break
                if kill_a > 0 or kill_b > 0:
                    gid = g.get("id")
                    t1 = g.get("opponent1", {}).get("fullName", "?")
                    t2 = g.get("opponent2", {}).get("fullName", "?")
                    bot.send_message(CHAT_ID, f"Auto start: {t1} vs {t2} | Map {map_num} | Kills {kill_a}-{kill_b}\ngame_id={gid}")
                    do_run(gid, map_num, CHAT_ID)
                    break
        except Exception as e:
            pass
# --- Init ---
load_session()
threading.Thread(target=watch_winner_needed, daemon=True).start()
threading.Thread(target=auto_monitor, daemon=True).start()
print(f"Bot started. Domain: {session['domain']}")
bot.infinity_polling()
