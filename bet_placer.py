# bet_placer.py
"""
Auto-betting module for melbet MLBB bot.
Flow: validate_coupon → place_bet → update bank → log.

Called from odds_logger.py when signal fires (cf < threshold).
Can also be tested standalone via __main__.
"""

import requests
from bot_log import log
from token_helper import get_token_seconds_left, format_state
import json
import uuid
import re
import os
import csv
from datetime import datetime

# ── Paths ─────────────────────────────────────────────────────────────────────
BASE_DIR  = r"D:\it\odds-logger-v2"
from paths import CURL_FILE
from paths import BANK_FILE
from paths import AUTO_BETS_FILE as BET_LOG

# ── Settings ──────────────────────────────────────────────────────────────────
BET_PCT      = 0.05   # 5% of bot bank per bet
MIN_BET      = 15     # melbet hard minimum (KGS)
CF_THRESHOLD = 1.20   # only bet if validate returns coef < this
CF_FLOOR     = 1.06   # do NOT bet if validate returns coef < this

# ── Melbet account constants (from your captured requests) ────────────────────
USER_ID  = 1538932801
PARTNER  = 8
GROUP    = 1439
COUNTRY  = 215        # UpdateCoupon only
CURRENCY = 93         # UpdateCoupon only (KGS internal code)

# ── Bank ──────────────────────────────────────────────────────────────────────
def load_bank():
    if not os.path.exists(BANK_FILE):
        default = {"balance": 7445.61, "initial": 7445.61, "bets_placed": 0}
        save_bank(default)
        log(f"[BANK] Created new bank: 7445.61 KGS. Edit {BANK_FILE} to change starting amount.")
        return default
    with open(BANK_FILE, encoding="utf-8") as f:
        return json.load(f)

def save_bank(bank):
    with open(BANK_FILE, "w", encoding="utf-8") as f:
        json.dump(bank, f, indent=2, ensure_ascii=False)

def calc_stake(balance):
    stake = round(balance * BET_PCT)
    return max(stake, MIN_BET)

# ── Session (reuse curl.txt, same as odds_logger) ────────────────────────────
def load_session():
    with open(CURL_FILE, encoding="utf-8-sig") as f:
        text = f.read()

    # Domain
    m = re.search(r"curl\s+['\"]?(https://[^/'\"?\s]+)", text)
    if not m:
        raise RuntimeError("Cannot parse domain from curl.txt")
    domain = m.group(1)

    # Cookies
    cookies = {}
    cm = re.search(r"-b\s+['\"]([^'\"]+)['\"]", text)
    if cm:
        for part in cm.group(1).split("; "):
            if "=" in part:
                k, v = part.split("=", 1)
                cookies[k.strip()] = v.strip()

    # x-hd
    xhd_m = re.search(r"['\"]x-hd:\s+([^'\"]+)['\"]", text)
    xhd = xhd_m.group(1).strip() if xhd_m else ""

    # x-auth: prefer explicit header, fall back to user_token cookie
    auth_m = re.search(r"['\"]x-auth:\s+Bearer\s+([^'\"]+)['\"]", text)
    if auth_m:
        xauth = f"Bearer {auth_m.group(1).strip()}"
    elif "user_token" in cookies:
        xauth = f"Bearer {cookies['user_token']}"
    else:
        xauth = ""

    return domain, cookies, xhd, xauth


def _check_token_expiry(bearer):
    """Best-effort JWT exp warning. Logs how many seconds until token dies."""
    import base64, time
    if not bearer or not bearer.startswith("Bearer "):
        log("[BOT] WARN: no Bearer token to check")
        return
    tok = bearer.split(" ", 1)[1]
    parts = tok.split(".")
    if len(parts) < 2:
        log("[BOT] WARN: token does not look like JWT")
        return
    try:
        payload_b64 = parts[1] + "=" * (-len(parts[1]) % 4)
        payload = json.loads(base64.urlsafe_b64decode(payload_b64))
        exp = payload.get("exp", 0)
        now = int(time.time())
        delta = exp - now
        if delta < 0:
            log(f"[BOT] !!! TOKEN EXPIRED {-delta}s ago. Refresh curl.txt + run update_session.py")
        elif delta < 300:
            log(f"[BOT] WARN: token expires in {delta}s")
        else:
            log(f"[BOT] token valid for {delta // 60}min")
    except Exception as e:
        log(f"[BOT] WARN: cannot decode token exp: {e}")


def _base_headers(xhd, xauth, domain="", app_name="__BETTING_APP__"):
    return {
        "accept": "application/json, text/plain, */*",
        "accept-language": "en-US,en;q=0.9,ru;q=0.8",
        "content-type": "application/json",
        "origin": domain,
        "dnt": "1",
        "is-srv": "false",
        "priority": "u=1, i",
        "sec-ch-ua": '"Google Chrome";v="147", "Not.A/Brand";v="8", "Chromium";v="147"',
        "sec-ch-ua-mobile": "?1",
        "sec-ch-ua-platform": '"Android"',
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-origin",
        "user-agent": (
            "Mozilla/5.0 (Linux; Android 6.0; Nexus 5 Build/MRA58N) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Mobile Safari/537.36"
        ),
        "x-app-n": app_name,
        "x-auth": xauth,
        "x-hd": xhd,
        "x-requested-with": "XMLHttpRequest",
        "x-svc-source": app_name,
    }


def _event_block(game_id, team_type, coef):
    return {
        "GameId": game_id,
        "Type": team_type,   # 1=team A, 3=team B
        "Coef": coef,
        "Param": 0,
        "PV": None,
        "PlayerId": 0,
        "Kind": 1,
        "InstrumentId": 0,
        "Seconds": 0,
        "Price": 0,
        "Expired": 0,
        "PlayersDuel": [],
    }

# ── API: balance ──────────────────────────────────────────────────────────────
def api_get_balance(domain, cookies, xhd, xauth):
    """Returns float or None."""
    url = f"{domain}/account-api/user/balance"
    hdrs = _base_headers(xhd, xauth, domain, "__V3_HOST_APP__")
    try:
        r = requests.get(url, headers=hdrs, cookies=cookies, timeout=10)
        r.raise_for_status()
        return r.json()["balance"][0]["money"]
    except Exception as e:
        log(f"[BALANCE] Error: {e}")
        return None

# ── API: validate (UpdateCoupon) ──────────────────────────────────────────────
def api_validate(domain, cookies, xhd, xauth, game_id, team_type, coef):
    """
    Returns dict:
      ok=True  → {ok, blocked, coef, min_bet, max_bet}
      ok=False → {ok, error}
    """
    url = f"{domain}/service-api/LiveBet-update/Open/UpdateCoupon"
    hdrs = _base_headers(xhd, xauth, domain, "__CYBER_APP__")
    payload = {
        "UserId": USER_ID,
        "Events": [_event_block(game_id, team_type, coef)],
        "Vid": 0,
        "partner": PARTNER,
        "Lng": "en",
        "CfView": 0,
        "CalcSystemsMin": False,
        "Group": GROUP,
        "Country": COUNTRY,
        "Currency": CURRENCY,
        "SaleBetId": 0,
        "IsPowerBet": False,
        "WithLobby": False,
        "IsExpressBoost": True,
    }
    try:
        r = requests.post(url, headers=hdrs, cookies=cookies, json=payload, timeout=10)
        r.raise_for_status()
        data = r.json()
        if not data.get("Success"):
            return {"ok": False, "error": data.get("Error", "unknown")}
        v = data["Value"]
        evt = v.get("Events", [{}])[0]
        return {
            "ok": True,
            "blocked": bool(evt.get("Block", False)),
            "finish": bool(evt.get("Finish", False)),
            "coef": float(v.get("Coef", coef)),
            "min_bet": int(v.get("minBet", 15)),
            "max_bet": int(v.get("maxBet", 999999)),
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}

# ── API: place (MakeBetWeb) ───────────────────────────────────────────────────
def api_place_bet(domain, cookies, xhd, xauth, game_id, team_type, coef, amount):
    """
    Returns dict: {success, bet_id, error, coef, amount, guid}
    """
    url = f"{domain}/service-api/LiveBet/Secure/MakeBetWeb"
    # user_token works for /Secure/ endpoint (confirmed from browser curl)
    _check_token_expiry(xauth)
    hdrs = _base_headers(xhd, xauth, domain)
    bet_guid = uuid.uuid4().hex[:24]
    payload = {
        "UserId": USER_ID,
        "Events": [_event_block(game_id, team_type, coef)],
        "Vid": 0,
        "partner": PARTNER,
        "Group": GROUP,
        "live": True,
        "CheckCf": 2,          # accept any coef change
        "Lng": "en",
        "notWait": True,
        "IsPowerBet": False,
        "Summ": amount,
        "isAutoBet": True,
        "autoBetCf": 0,
        "TransformEventKind": True,
        "autoBetCfView": 0,
        "Source": 55,
        "OneClickBet": 2,
    }
    try:
        r = requests.post(url, headers=hdrs, cookies=cookies, json=payload, timeout=15)
        if r.status_code == 401 or r.status_code == 403:
            log(f"[BOT] HTTP {r.status_code} on MakeBetWeb. URL={url}")
            log(f"[BOT] Response body: {r.text[:500]}")
            log(f"[BOT] Used x-auth: {xauth[:30]}... (len={len(xauth)})")
            log(f"[BOT] cookies sent: {sorted(cookies.keys())}")
            return {"success": False, "error": f"HTTP {r.status_code}: {r.text[:200]}",
                    "error_code": r.status_code, "coef": coef, "amount": amount, "guid": bet_guid}
        r.raise_for_status()
        data = r.json()
        if not data.get("Success", False):
            log(f"[BOT] Server returned Success=false. Full response: {json.dumps(data)[:500]}")
        return {
            "success": bool(data.get("Success", False)),
            "bet_id": data.get("Id", 0),
            "error": data.get("Error", ""),
            "error_code": data.get("ErrorCode", 0),
            "coef": coef,
            "amount": amount,
            "guid": bet_guid,
        }
    except requests.HTTPError as e:
        log(f"[BOT] HTTPError: {e}. Body: {getattr(e.response, 'text', '')[:300]}")
        return {"success": False, "error": str(e), "coef": coef, "amount": amount, "guid": ""}
    except Exception as e:
        return {"success": False, "error": str(e), "coef": coef, "amount": amount, "guid": ""}

# ── Logging ───────────────────────────────────────────────────────────────────
BET_LOG_COLS = [
    "timestamp", "game_id", "map_id", "team_type",
    "signal_coef", "validated_coef", "amount",
    "success", "bet_id", "error", "error_code",
    "bank_before", "bank_after", "guid",
]

def log_bet_result(result, game_id, map_id, team_type, signal_coef, bank_before, bank_after):
    write_header = not os.path.exists(BET_LOG)
    with open(BET_LOG, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if write_header:
            w.writerow(BET_LOG_COLS)
        w.writerow([
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            game_id, map_id, team_type,
            signal_coef,
            result.get("coef", signal_coef),
            result.get("amount", 0),
            result.get("success", False),
            result.get("bet_id", ""),
            result.get("error", ""),
            result.get("error_code", ""),
            round(bank_before, 2),
            round(bank_after, 2),
            result.get("guid", ""),
        ])

# ── Main entry point ──────────────────────────────────────────────────────────
def auto_bet(game_id, map_id, team_type, signal_coef):
    """
    Full bet flow. Called from odds_logger when signal fires.

    Args:
        game_id     : int  — melbet GameId (subgame / map id)
        map_id      : str  — "1"/"2"/"3" map number (for logging)
        team_type   : int  — 1=team A, 3=team B
        signal_coef : float — coef at signal moment

    Returns:
        True if bet placed, False otherwise.
    """
    ts = datetime.now().strftime("%H:%M:%S")
    log(f"[BOT] ▶ Signal: game={game_id} map={map_id} team={'A' if team_type==1 else 'B'} cf={signal_coef:.3f}")

    # Load session
    try:
        domain, cookies, xhd, xauth = load_session()
    except Exception as e:
        log(f"[BOT] Session load failed: {e}")
        return False

    # Bank
    bank = load_bank()
    bank_before = bank["balance"]
    stake = calc_stake(bank_before)
    log(f"[BOT] Bank={bank_before:.0f} KGS  Stake={stake} KGS (5%)")

    secs_left, tok_err = get_token_seconds_left()
    if tok_err is not None or secs_left is None or secs_left <= 0:
        log("[BOT] PRE-FLIGHT FAIL: " + format_state(secs_left, tok_err) + " - skipping bet")
        try:
            import requests as _rq
            from paths import TG_ALERT_TOKEN as _tk, TG_CHAT_ID as _cid
            _rq.post(
                f"https://api.telegram.org/bot{_tk}/sendMessage",
                json={"chat_id": _cid,
                      "text": "[BOT] Token issue: " + format_state(secs_left, tok_err) + ". Refresh curl.txt + run update_session.py"},
                timeout=5,
            )
        except Exception:
            pass
        return False

    # Step 1: validate
    val = api_validate(domain, cookies, xhd, xauth, game_id, team_type, signal_coef)
    if not val["ok"]:
        log(f"[BOT] ✗ Validate error: {val['error']}")
        return False
    if val["blocked"] or val["finish"]:
        log(f"[BOT] ✗ Market blocked/finished — skip")
        return False

    live_coef = val["coef"]
    log(f"[BOT] Validated coef: {live_coef:.3f} (signal was {signal_coef:.3f})")

    if live_coef >= CF_THRESHOLD:
        log(f"[BOT] ✗ Coef shifted above threshold ({live_coef:.3f} ≥ {CF_THRESHOLD}) — skip")
        return False

    if live_coef < CF_FLOOR:
        log(f"[BOT] skip: cf={live_coef:.3f} below floor {CF_FLOOR} (market about to close)")
        return False

    # Clamp stake to server limits
    stake = max(stake, val["min_bet"])
    stake = min(stake, val["max_bet"])

    # Step 2: place
    result = api_place_bet(domain, cookies, xhd, xauth, game_id, team_type, live_coef, stake)

    # Bank update
    if result["success"]:
        bank["balance"] -= stake   # deduct; wins reconciled manually via build_excel
        bank["bets_placed"] += 1
        save_bank(bank)
        log(f"[BOT] ✓ BET PLACED  {stake} KGS @ {live_coef:.3f}  ID={result['bet_id']}")
    else:
        log(f"[BOT] ✗ Bet failed: [{result.get('error_code')}] {result['error']}")
        # diagnostic: where did market go?
        try:
            post = api_validate(domain, cookies, xhd, xauth, game_id, team_type, live_coef)
            if post["ok"]:
                log("[BOT] post-fail state: cf=" + str(post["coef"]) + " blocked=" + str(post["blocked"]) + " finish=" + str(post["finish"]))
            else:
                log("[BOT] post-fail validate error: " + str(post["error"]))
        except Exception as _e:
            log("[BOT] post-fail validate crashed: " + str(_e))

    # Log always (even failures)
    log_bet_result(result, game_id, map_id, team_type,
                   signal_coef, bank_before, bank["balance"])

    return result["success"]


# ── Standalone test ───────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("=== bet_placer standalone test ===")
    domain, cookies, xhd, xauth = load_session()
    print(f"Domain: {domain}")

    bal = api_get_balance(domain, cookies, xhd, xauth)
    print(f"Main account balance: {bal} KGS")

    bank = load_bank()
    print(f"Bot bank: {bank['balance']} KGS (initial: {bank['initial']})")
    print(f"Bets placed so far: {bank['bets_placed']}")

    print("\nTo test a real validate, run:")
    print("  from bet_placer import *")
    print("  load_session() → domain, cookies, xhd, xauth")
    print("  api_validate(domain, cookies, xhd, xauth, GAME_ID, 1, 1.10)")
