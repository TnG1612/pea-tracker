# pea-tracker

A free, automatic daily price tracker for about 290 stocks and ETFs
(Paris, Frankfurt, Amsterdam, Milan, Madrid, London, Zurich, US, Asia).

Every weekday evening, GitHub runs a small Python script that downloads the latest
**closing prices** from Yahoo Finance and saves them in [`prices.json`](prices.json).
Any other tool can read that file from its "raw" URL.

## What's in here

| File | What it does |
|---|---|
| `tickers.csv` | The list of assets (one line each, the `id` column is the key) |
| `yahoo_map.csv` | Each `id` and its Yahoo Finance ticker (made by `build_yahoo_map.py`) |
| `fetch_prices.py` | Downloads prices and writes `prices.json` + `history/YYYY.csv` |
| `tests/test_prices.py` | Safety checks run before anything is saved |
| `.github/workflows/prices.yml` | The schedule: weekdays 17:00 and 21:30 UTC, plus a manual button |

## The output: `prices.json`

```json
{
  "generatedAt": "2026-11-13T21:30:05+00:00",
  "prices": {
    "AI": {"id": "AI", "yahoo_ticker": "AI.PA", "price": 192.84, "currency": "EUR",
           "chg1d": 0.35, "chgYtd": 32.36, "date": "2026-11-12"}
  },
  "missing": ["ROG"]
}
```

- `price`: the last **closing** price (never a live price during the trading day)
- `chg1d`: % change vs the previous close. `chgYtd`: % change vs the last close of last year
- `currency`: as reported by Yahoo. **London prices are in `GBp` (pence)**: divide by 100 for pounds
- `date`: the trading day of that close
- `fx`: how many euros 1 unit of each currency is worth (e.g. `"USD": 0.90`), to add up a portfolio in euros
- `missing`: ids that could not be fetched. If we had an older price, it is kept and marked `"stale": true`

The script **never invents a number**. If something fails, it says so in `missing`.

`history/YYYY.csv` keeps one line per day and asset (`date,id,close`) for future charts.

## Run it on your own computer

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows  (Mac/Linux: source .venv/bin/activate)
pip install -r requirements.txt
python fetch_prices.py          # writes prices.json
python -m pytest                # checks it
```

## Adding an asset

1. Add a line to `tickers.csv`
2. Run `python build_yahoo_map.py` and check the rows marked `check` or `unmapped`
3. Commit both files

## Good to know

- Data comes from Yahoo Finance through the unofficial `yfinance` library: free, but with no guarantee.
  A fallback to Stooq is coded, but Stooq currently blocks automated downloads.
- `chgYtd` uses plain closing prices (dividends are not added back).
- This is a personal hobby project, not investment advice.
