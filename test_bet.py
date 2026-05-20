# test_bet.py — one-shot bet test. Run: python test_bet.py
# Works for both live and pre-match (line) bets.

from bet_placer import load_session, api_validate, api_place_bet, _base_headers, USER_ID, PARTNER, GROUP
import json, uuid, requests

# ── EDIT THESE ────────────────────────────────────────────────────────────────
GAME_ID   = 719554590
TEAM_TYPE = 1        # A
COEF      = 2.336
AMOUNT    = 15       # minimum
IS_LIVE   = True     # live bet
# ─────────────────────────────────────────────────────────────────────────────

domain, cookies, xhd, xauth = load_session()
print(f"Domain  : {domain}")
print(f"GameId  : {GAME_ID}")
print(f"Live    : {IS_LIVE}")
print(f"Team    : {'A' if TEAM_TYPE==1 else 'B'}  Coef: {COEF}")

print("\n[1] Validating (UpdateCoupon)...")
val = api_validate(domain, cookies, xhd, xauth, GAME_ID, TEAM_TYPE, COEF)
print(json.dumps(val, indent=2, ensure_ascii=False))

if not val.get("ok"):
    print("\nValidate failed — stopping.")
    exit(1)

# if val.get("blocked") or val.get("finish"):
#     print("\nMarket blocked/finished — stopping.")
#     exit(1)

live_coef = val["coef"]
print(f"\nServer coef: {live_coef}")

print(f"\n[2] Placing {AMOUNT} KGS @ {live_coef} ...")

# Call api_place_bet but override live flag via direct request
url = f"{domain}/service-api/LiveBet/Secure/MakeBetWeb"
hdrs = _base_headers(xhd, xauth, domain)
payload = {
    "UserId": USER_ID,
    "Events": [{
        "GameId": GAME_ID, 
        "Type": TEAM_TYPE, 
        "Coef": live_coef,
        "Param": 0, 
        "PV": 0,           # Сменили с None на 0
        "PlayerId": 0, 
        "Kind": 0,         # Если не сработает, попробуй 0
        "InstrumentId": 0, 
        "Seconds": 0, 
        "Price": 0, 
        "Expired": 0,
        "PlayersDuel": [],
    }],
    "Vid": 0, 
    "partner": PARTNER, 
    "Group": GROUP,
    "live": IS_LIVE,
    "CheckCf": 2, 
    "Lng": "en", 
    "notWait": True,
    "betGUID": uuid.uuid4().hex[:24],
    "IsPowerBet": False, 
    "Summ": AMOUNT,
    "isAutoBet": True, 
    "autoBetCf": 0,
    "TransformEventKind": True, 
    "autoBetCfView": 0,
    "Source": 2,           # Сменили с 55 на 2 (Desktop)
    "OneClickBet": 2,
}

r = requests.post(url, headers=hdrs, cookies=cookies, json=payload, timeout=15)
print(f"HTTP {r.status_code}")
try:
    data = r.json()
    print(json.dumps(data, indent=2, ensure_ascii=False))
except Exception:
    print(r.text[:500])
