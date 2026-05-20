# odds-logger-v2

A personal research project for logging and analyzing real-time event data from a public sports API. The system polls a live data feed, persists every observation as a time series, and runs back-tested entry rules over the accumulated dataset.

This is a pet project — not a product, not a service. Sharing the code as a self-contained example of a small data pipeline.

## Stack

- **Python 3.10+**
- `requests` — HTTP polling
- `openpyxl` — Excel report generation
- `pyTelegramBotAPI` — remote control + alerts via Telegram
- Plain CSV/JSON for storage (no DB, no ORM — keeps it readable and grep-able)
- Threading for non-blocking alerts and IPC between the logger and the Telegram bot

## Architecture

```
                ┌────────────────────┐
                │   external API     │
                └─────────┬──────────┘
                          │ poll every 3s
                          ▼
   ┌──────────────────────────────────────────┐
   │           odds_logger.py                 │
   │  • parses tick data                      │
   │  • writes one row per tick to CSV        │
   │  • detects event boundaries              │
   │  • writes summary row on each closure    │
   │  • sends Telegram alerts on triggers     │
   └──────┬───────────────────┬───────────────┘
          │ writes            │ alerts
          ▼                   ▼
   ┌─────────────┐    ┌─────────────────┐
   │  data/*.csv │    │  Telegram bot   │
   └──────┬──────┘    └─────────────────┘
          │
          │ reads
          ▼
   ┌──────────────────────┐    ┌─────────────────┐
   │  backtest.py         │    │  build_excel.py │
   │  multi-strategy      │    │  multi-sheet    │
   │  simulator           │    │  XLSX report    │
   └──────────────────────┘    └─────────────────┘
```

## Layout

```
odds-logger-v2/
├── paths.py            central config: paths + secrets loader
├── odds_logger.py      main poller
├── backtest.py         strategy simulator
├── build_excel.py      report generator
├── tg_bot.py           Telegram remote control
├── update_session.py   session bootstrap from a curl snippet
├── token_helper.py     JWT expiry checker
├── bot_log.py          shared logging module
├── data/               accumulated CSV/JSON (gitignored)
├── output/             generated reports (gitignored)
└── extras/             unrelated standalone tools
```

## Setup

```bash
pip install -r requirements.txt
cp .env.example .env       # fill in your Telegram bot tokens
```

You also need a fresh session captured as a cURL command (placed in `curl.txt`), then:

```bash
python update_session.py   # patches session details into the logger
python odds_logger.py      # starts polling
python backtest.py         # runs strategy simulation against accumulated data
python build_excel.py      # builds the Excel dashboard
```

## Design notes I liked

- **One central `paths.py`** — every other module imports its paths and secrets from there. Moving `data/` to a different drive is a one-line change.
- **`.env` parser is ~15 lines** of stdlib — no `python-dotenv` dependency for something this small.
- **Backtest strategies are plain functions** with the same `(ticks) → list[bet]` signature. Adding a new rule is one function + one line in a registry list.
- **The Telegram bot and the logger don't import each other.** They communicate via two marker files (`winner_needed.txt`, `winner_answer.txt`). Crude but unbreakable.
- **No databases.** CSV-only. Means `grep`, `cut`, `awk`, and Excel all work directly on the data.

## What I'd do differently

- The session-refresh dance (`curl.txt` → `update_session.py` → restart) is clunky. A proper headless-browser session capture would be cleaner.
- `build_excel.py` is one big script. Should be split into one file per sheet.
- Some early code has mojibake in comments from an editor encoding mismatch. Mostly cleaned up but not 100%.

## Status

Active but slow — runs in the background, accumulates data, gets occasional tweaks when something interesting shows up in the backtest.

## License

No license. Personal code, public for reference.
