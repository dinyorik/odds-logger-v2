"""
backtest.py — симуляция стратегий на накопленных тиках odds_log.csv

Читает: odds_log.csv + matches.csv (для winner)
Пишет: backtest_results.csv + сводка в консоль
Опц.: --detail → backtest_details.csv с каждой ставкой

Стратегии:
  naive          — первое cf<=1.20 при OPEN, ставка на эту команду
  kill_aware_0   — то же + фильтр killdiff >= 0 у команды на которую ставим
  kill_aware_2   — то же + killdiff >= 2
  kill_aware_3   — то же + killdiff >= 3
  second_window  — игнорим первый OPEN, ждём BLOCK→OPEN.
                   Если фаворит сменился И его pre-block cf >= 1.5 → ставим
  stairstep      — лесенкой 50 @ 1.20, 75 @ 1.10, 100 @ 1.05 на одну команду
  combined       — kill_aware_2 ИЛИ second_window (что сработает раньше)

Размер ставки: 100 KGS (для stairstep — 50/75/100). ROI считается как
profit / total_stake.
"""

import csv
import os
import argparse
from collections import defaultdict

from paths import LOG_FILE
from paths import MATCHES_FILE
from paths import BACKTEST_RESULTS_FILE as OUTPUT_FILE

CF_THR = 1.20
CF_PRE_BLOCK_LOSER_MIN = 1.5  # second_window: pre-block cf проигрывающего >= этого


def to_float(s):
    try:
        return float(s) if s not in ("", None) else None
    except (ValueError, TypeError):
        return None


def parse_score(s):
    if not s or "-" not in s:
        return None, None
    try:
        a, b = s.split("-")
        return int(a), int(b)
    except (ValueError, TypeError):
        return None, None


def load_winners(path):
    winners = {}
    if not os.path.exists(path):
        return winners
    with open(path, encoding="utf-8") as f:
        r = csv.DictReader(f)
        for row in r:
            if row.get("winner") in ("A", "B"):
                key = (row["match_id"], str(row["map"]))
                winners[key] = row["winner"]
    return winners


def load_ticks(path):
    by_match = defaultdict(list)
    if not os.path.exists(path):
        return by_match
    with open(path, encoding="utf-8") as f:
        r = csv.DictReader(f)
        for row in r:
            key = (row["match_id"], str(row["map"]))
            by_match[key].append(row)
    return by_match


# ---------------- strategies ----------------

def strat_naive(ticks):
    bets = []
    for tick in ticks:
        if tick["blocked"] == "True":
            continue
        cf_a, cf_b = to_float(tick["cf_team_a"]), to_float(tick["cf_team_b"])
        if cf_a is None or cf_b is None:
            continue
        if cf_a <= CF_THR and cf_b <= CF_THR:
            t, cf = ("A", cf_a) if cf_a <= cf_b else ("B", cf_b)
        elif cf_a <= CF_THR:
            t, cf = "A", cf_a
        elif cf_b <= CF_THR:
            t, cf = "B", cf_b
        else:
            continue
        bets.append((t, cf, 100))
        break
    return bets


def strat_kill_aware(ticks, min_kdiff):
    bets = []
    for tick in ticks:
        if tick["blocked"] == "True":
            continue
        cf_a, cf_b = to_float(tick["cf_team_a"]), to_float(tick["cf_team_b"])
        if cf_a is None or cf_b is None:
            continue
        sa, sb = parse_score(tick["score"])
        if sa is None:
            continue
        kdiff_a, kdiff_b = sa - sb, sb - sa
        if cf_a <= CF_THR and kdiff_a >= min_kdiff:
            bets.append(("A", cf_a, 100))
            break
        if cf_b <= CF_THR and kdiff_b >= min_kdiff:
            bets.append(("B", cf_b, 100))
            break
    return bets


def strat_second_window(ticks):
    bets = []
    last_open_a = last_open_b = None
    pre_a = pre_b = None
    was_blocked = False
    for tick in ticks:
        cf_a, cf_b = to_float(tick["cf_team_a"]), to_float(tick["cf_team_b"])
        if cf_a is None or cf_b is None:
            continue
        if tick["blocked"] == "True":
            if not was_blocked and last_open_a is not None:
                pre_a, pre_b = last_open_a, last_open_b
            was_blocked = True
            continue
        last_open_a, last_open_b = cf_a, cf_b
        if not was_blocked or pre_a is None:
            continue
        pre_fav = "A" if pre_a < pre_b else "B"
        cur_fav = "A" if cf_a < cf_b else "B"
        if cur_fav == pre_fav:
            continue
        if cur_fav == "A" and pre_a >= CF_PRE_BLOCK_LOSER_MIN and cf_a <= CF_THR:
            bets.append(("A", cf_a, 100))
            break
        if cur_fav == "B" and pre_b >= CF_PRE_BLOCK_LOSER_MIN and cf_b <= CF_THR:
            bets.append(("B", cf_b, 100))
            break
    return bets


def strat_stairstep(ticks):
    bets = []
    team = None
    hit = set()
    for tick in ticks:
        if tick["blocked"] == "True":
            continue
        cf_a, cf_b = to_float(tick["cf_team_a"]), to_float(tick["cf_team_b"])
        if cf_a is None or cf_b is None:
            continue
        if team is None:
            if cf_a <= 1.20 and cf_b <= 1.20:
                team = "A" if cf_a <= cf_b else "B"
            elif cf_a <= 1.20:
                team = "A"
            elif cf_b <= 1.20:
                team = "B"
            else:
                continue
        cur = cf_a if team == "A" else cf_b
        if cur <= 1.20 and "120" not in hit:
            bets.append((team, cur, 50))
            hit.add("120")
        if cur <= 1.10 and "110" not in hit:
            bets.append((team, cur, 75))
            hit.add("110")
        if cur <= 1.05 and "105" not in hit:
            bets.append((team, cur, 100))
            hit.add("105")
        if len(hit) == 3:
            break
    return bets


def strat_combined(ticks, min_kdiff=2):
    bets = []
    last_open_a = last_open_b = None
    pre_a = pre_b = None
    was_blocked = False
    for tick in ticks:
        cf_a, cf_b = to_float(tick["cf_team_a"]), to_float(tick["cf_team_b"])
        if cf_a is None or cf_b is None:
            continue
        if tick["blocked"] == "True":
            if not was_blocked and last_open_a is not None:
                pre_a, pre_b = last_open_a, last_open_b
            was_blocked = True
            continue
        last_open_a, last_open_b = cf_a, cf_b

        # 1. kill_aware
        sa, sb = parse_score(tick["score"])
        if sa is not None:
            kdiff_a, kdiff_b = sa - sb, sb - sa
            if cf_a <= CF_THR and kdiff_a >= min_kdiff:
                bets.append(("A", cf_a, 100))
                break
            if cf_b <= CF_THR and kdiff_b >= min_kdiff:
                bets.append(("B", cf_b, 100))
                break
        # 2. second_window
        if was_blocked and pre_a is not None:
            pre_fav = "A" if pre_a < pre_b else "B"
            cur_fav = "A" if cf_a < cf_b else "B"
            if cur_fav != pre_fav:
                if cur_fav == "A" and pre_a >= CF_PRE_BLOCK_LOSER_MIN and cf_a <= CF_THR:
                    bets.append(("A", cf_a, 100))
                    break
                if cur_fav == "B" and pre_b >= CF_PRE_BLOCK_LOSER_MIN and cf_b <= CF_THR:
                    bets.append(("B", cf_b, 100))
                    break
    return bets



def strat_kill_burst(ticks, window=5, burst=3):
    """
    Bet on team T if cf <= 1.20 AND T scored at least `burst` more kills than the
    other team in the last `window` ticks. Ignores absolute killdiff.
    """
    bets = []
    history = []  # list of (sa, sb)
    for tick in ticks:
        sa, sb = parse_score(tick["score"])
        if sa is None:
            continue
        history.append((sa, sb))
        if tick["blocked"] == "True":
            continue
        cf_a, cf_b = to_float(tick["cf_team_a"]), to_float(tick["cf_team_b"])
        if cf_a is None or cf_b is None:
            continue
        if len(history) < window + 1:
            continue
        sa_old, sb_old = history[-window - 1]
        delta_a = (sa - sa_old) - (sb - sb_old)  # net kill swing toward A
        delta_b = -delta_a
        if cf_a <= CF_THR and delta_a >= burst:
            bets.append(("A", cf_a, 100))
            break
        if cf_b <= CF_THR and delta_b >= burst:
            bets.append(("B", cf_b, 100))
            break
    return bets


def strat_kill_aware_or_burst(ticks, window=5, burst=3):
    """
    Bet on team T if cf <= 1.20 AND (T not behind in absolute kills
    OR T had a kill burst >= `burst` in last `window` ticks).
    """
    bets = []
    history = []
    for tick in ticks:
        sa, sb = parse_score(tick["score"])
        if sa is None:
            continue
        history.append((sa, sb))
        if tick["blocked"] == "True":
            continue
        cf_a, cf_b = to_float(tick["cf_team_a"]), to_float(tick["cf_team_b"])
        if cf_a is None or cf_b is None:
            continue

        kdiff_a, kdiff_b = sa - sb, sb - sa

        delta_a = delta_b = 0
        if len(history) >= window + 1:
            sa_old, sb_old = history[-window - 1]
            delta_a = (sa - sa_old) - (sb - sb_old)
            delta_b = -delta_a

        if cf_a <= CF_THR and (kdiff_a >= 0 or delta_a >= burst):
            bets.append(("A", cf_a, 100))
            break
        if cf_b <= CF_THR and (kdiff_b >= 0 or delta_b >= burst):
            bets.append(("B", cf_b, 100))
            break
    return bets


# ---------------- evaluation ----------------

def evaluate(bets, winner):
    n = len(bets)
    wins = sum(1 for (t, _, _) in bets if t == winner)
    losses = n - wins
    stake = sum(s for (_, _, s) in bets)
    ret = sum(s * cf for (t, cf, s) in bets if t == winner)
    profit = ret - stake
    avg_cf = sum(cf * s for (_, cf, s) in bets) / stake if stake else 0
    return n, wins, losses, stake, ret, profit, avg_cf


def run(name, fn, ticks_by_match, winners):
    tot_bets = tot_wins = tot_losses = 0
    tot_stake = tot_ret = 0.0
    cf_w_sum = 0.0
    matches_bet = 0
    matches_total = 0
    details = []
    for key, ticks in ticks_by_match.items():
        winner = winners.get(key)
        if winner is None:
            continue
        matches_total += 1
        bets = fn(ticks)
        if not bets:
            continue
        matches_bet += 1
        n, w, l, s, r, p, cf = evaluate(bets, winner)
        tot_bets += n
        tot_wins += w
        tot_losses += l
        tot_stake += s
        tot_ret += r
        cf_w_sum += cf * s
        for (team, c, st) in bets:
            details.append([name, key[0], key[1], team, c, st,
                            "win" if team == winner else "loss", winner])
    profit = tot_ret - tot_stake
    wr = (tot_wins / tot_bets * 100) if tot_bets else 0
    avg_cf = (cf_w_sum / tot_stake) if tot_stake else 0
    roi = (profit / tot_stake * 100) if tot_stake else 0
    return {
        "strategy": name,
        "matches_total": matches_total,
        "matches_bet": matches_bet,
        "bets": tot_bets,
        "wins": tot_wins,
        "losses": tot_losses,
        "wr_pct": round(wr, 1),
        "avg_cf": round(avg_cf, 4),
        "stake": round(tot_stake, 0),
        "profit": round(profit, 1),
        "roi_pct": round(roi, 2),
    }, details


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--strategy", default="all")
    ap.add_argument("--detail", action="store_true")
    args = ap.parse_args()

    print(f"Loading {MATCHES_FILE}...")
    winners = load_winners(MATCHES_FILE)
    print(f"  {len(winners)} matches with winner")

    print(f"Loading {LOG_FILE}...")
    ticks = load_ticks(LOG_FILE)
    print(f"  {len(ticks)} (match, map) groups")

    overlap = set(winners) & set(ticks)
    print(f"  {len(overlap)} testable (have winner AND ticks)")
    print()

    strats = [
        ("naive", strat_naive),
        ("kill_aware_0", lambda t: strat_kill_aware(t, 0)),
        ("kill_aware_2", lambda t: strat_kill_aware(t, 2)),
        ("kill_aware_3", lambda t: strat_kill_aware(t, 3)),
        ("kill_burst", lambda t: strat_kill_burst(t, window=5, burst=3)),
        ("kill_aware_or_burst", lambda t: strat_kill_aware_or_burst(t, window=5, burst=3)),
        ("second_window", strat_second_window),
        ("stairstep", strat_stairstep),
        ("combined", strat_combined),
    ]
    if args.strategy != "all":
        wanted = set(args.strategy.split(","))
        strats = [(n, f) for (n, f) in strats if n in wanted]

    results = []
    all_details = []
    for name, fn in strats:
        s, d = run(name, fn, ticks, winners)
        results.append(s)
        all_details.extend(d)

    cols = ["strategy", "matches_bet", "bets", "wins", "losses",
            "wr_pct", "avg_cf", "stake", "profit", "roi_pct"]
    widths = {c: max(len(c), max((len(str(r[c])) for r in results), default=0))
              for c in cols}
    print(" | ".join(c.ljust(widths[c]) for c in cols))
    print("-+-".join("-" * widths[c] for c in cols))
    for r in results:
        print(" | ".join(str(r[c]).ljust(widths[c]) for c in cols))
    print()

    with open(OUTPUT_FILE, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(cols)
        for r in results:
            w.writerow([r[c] for c in cols])
    print(f"-> {OUTPUT_FILE}")

    if args.detail:
        with open(BACKTEST_DETAILS_FILE, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["strategy", "match_id", "map", "team", "cf",
                        "stake", "result", "winner"])
            for row in all_details:
                w.writerow(row)
        print("-> backtest_details.csv")

    print()
    for r in results:
        if r["bets"] < 20:
            print(f"⚠ {r['strategy']}: всего {r['bets']} ставок - стат значимости мало")


if __name__ == "__main__":
    main()
