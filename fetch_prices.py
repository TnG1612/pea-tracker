"""
fetch_prices.py - download the latest daily closing prices and save them to prices.json.

    python fetch_prices.py

Reads yahoo_map.csv (id -> Yahoo ticker), writes prices.json and appends history/YYYY.csv.
Golden rule: never invent a number. If a ticker fails, its id goes into "missing"
and we keep the last good price we had (marked "stale": true).
"""
import csv
import io
import json
import os
from datetime import datetime, timezone, time as dtime
from zoneinfo import ZoneInfo

import pandas as pd
import requests
import yfinance as yf

PRICES_FILE = "prices.json"

# When each market closes (local time, plus a few minutes of margin).
# Until then, today's row is still moving, so we must NOT treat it as a close.
MARKET_CLOSE = {
    "": ("America/New_York", dtime(16, 10)),        # US tickers have no suffix
    ".PA": ("Europe/Paris", dtime(17, 45)), ".AS": ("Europe/Paris", dtime(17, 45)),
    ".DE": ("Europe/Paris", dtime(17, 45)), ".MI": ("Europe/Paris", dtime(17, 45)),
    ".MC": ("Europe/Paris", dtime(17, 45)), ".BR": ("Europe/Paris", dtime(17, 45)),
    ".HE": ("Europe/Helsinki", dtime(18, 40)), ".ST": ("Europe/Stockholm", dtime(17, 40)),
    ".CO": ("Europe/Copenhagen", dtime(17, 10)), ".SW": ("Europe/Zurich", dtime(17, 40)),
    ".L": ("Europe/London", dtime(16, 45)), ".T": ("Asia/Tokyo", dtime(15, 45)),
    ".HK": ("Asia/Hong_Kong", dtime(16, 20)), ".KS": ("Asia/Seoul", dtime(15, 45)),
}


def suffix(ticker):
    """'AI.PA' -> '.PA', 'AAPL' -> ''"""
    return "." + ticker.rsplit(".", 1)[1] if "." in ticker else ""


def drop_unfinished_day(ticker, closes):
    """Remove today's row if that market has not closed yet (it would be a live price)."""
    tz_name, close_time = MARKET_CLOSE.get(suffix(ticker), MARKET_CLOSE[""])
    now = datetime.now(ZoneInfo(tz_name))
    if len(closes) and closes.index[-1].date() == now.date() and now.time() < close_time:
        return closes.iloc[:-1]
    return closes


def load_map():
    """Read yahoo_map.csv -> list of (id, yahoo_ticker, currency) for mapped rows."""
    with open("yahoo_map.csv", encoding="utf-8") as f:
        return [(r["id"], r["yahoo_ticker"], r["yahoo_currency"])
                for r in csv.DictReader(f) if r["yahoo_ticker"]]


def download_yahoo(tickers, start):
    """One batch download of daily closes. Returns {ticker: pandas Series of closes}."""
    data = yf.download(tickers, start=start, auto_adjust=False, group_by="ticker",
                       progress=False, threads=True)
    out = {}
    for t in tickers:
        try:
            out[t] = data[t]["Close"].dropna()
        except KeyError:
            out[t] = pd.Series(dtype=float)
    return out


def download_stooq(tickers, start):
    """Fallback: Stooq free CSV files. Only some markets exist there (US, Xetra, London, Tokyo, HK)."""
    stooq_suffix = {"": ".us", ".DE": ".de", ".L": ".uk", ".T": ".jp", ".HK": ".hk"}
    out = {}
    for t in tickers:
        sfx = suffix(t)
        if sfx not in stooq_suffix:
            continue
        symbol = (t[: -len(sfx)] if sfx else t).replace("-", ".").lower() + stooq_suffix[sfx]
        try:
            url = f"https://stooq.com/q/d/l/?s={symbol}&i=d&d1={start.replace('-', '')}"
            text = requests.get(url, timeout=20).text
            df = pd.read_csv(io.StringIO(text), parse_dates=["Date"], index_col="Date")
            out[t] = df["Close"].dropna()
        except Exception:
            pass                                          # not available -> stays missing
    return out


def fetch_fx(currencies):
    """{'USD': 0.86, ...} = euros per 1 unit. Yahoo 'EURUSD=X' gives dollars per 1 euro, so we invert it."""
    codes = sorted({"GBP" if c == "GBp" else c for c in currencies} - {"EUR", ""})
    fx = {"EUR": 1.0}
    try:
        data = yf.download([f"EUR{c}=X" for c in codes], period="10d", progress=False, group_by="ticker")
        for c in codes:
            s = data[f"EUR{c}=X"]["Close"].dropna()
            if len(s) and s.iloc[-1] > 0:
                fx[c] = round(1 / float(s.iloc[-1]), 8)
    except Exception as e:
        print("Exchange rates failed:", e)
    if "GBP" in fx:
        fx["GBp"] = round(fx["GBP"] / 100, 10)              # London quotes in pence
    return fx if len(fx) > 1 else {}


def pct(new, old):
    """Percentage change, rounded to 2 decimals."""
    return round((new / old - 1) * 100, 2)


def main():
    assets = load_map()
    all_ids = [row["id"] for row in csv.DictReader(open("tickers.csv", encoding="utf-8"))]
    tickers = sorted({t for _, t, _ in assets})
    year = datetime.now(timezone.utc).year
    start = f"{year - 1}-12-01"                           # enough to find last year's final close

    # 1) Download: Yahoo first, Stooq only if Yahoo failed completely
    try:
        closes = download_yahoo(tickers, start)
    except Exception as e:
        print("Yahoo download crashed:", e)
        closes = {}
    if not any(len(s) for s in closes.values()):
        print("Yahoo returned nothing - trying Stooq fallback")
        closes = download_stooq(tickers, start)

    # 2) Previous prices.json, used to keep old values for failed tickers
    old_file = {}
    if os.path.exists(PRICES_FILE):
        old_file = json.load(open(PRICES_FILE, encoding="utf-8"))
    old = old_file.get("prices", {})

    # 3) Compute the numbers for each id
    prices, missing, history_rows = {}, [], []
    for asset_id, ticker, currency in assets:
        s = drop_unfinished_day(ticker, closes.get(ticker, pd.Series(dtype=float)))
        s = s[s > 0]                                      # a price of 0 or less is bad data
        if len(s) < 2:
            missing.append(asset_id)
            continue
        last_year = s[s.index.year < year]                # closes from before 1 January
        price = float(s.iloc[-1])
        day = s.index[-1].strftime("%Y-%m-%d")
        prices[asset_id] = {
            "id": asset_id,
            "yahoo_ticker": ticker,
            "price": round(price, 4),
            "currency": currency,                         # note: London prices are in GBp (pence)
            "chg1d": pct(price, float(s.iloc[-2])),
            "chgYtd": pct(price, float(last_year.iloc[-1])) if len(last_year) else None,
            "date": day,
        }
        history_rows.append({"date": day, "id": asset_id, "close": round(price, 4)})

    # ids with no Yahoo ticker at all are missing too
    mapped = {a for a, _, _ in assets}
    missing += [i for i in all_ids if i not in mapped]
    # keep the previous good value for anything that failed today (clearly flagged)
    for asset_id in missing:
        if asset_id in old:
            prices[asset_id] = {**old[asset_id], "stale": True}

    # 4) Exchange rates: how many euros 1 unit of each currency is worth (for portfolio totals)
    fx = fetch_fx({p["currency"] for p in prices.values()}) or old_file.get("fx", {})

    # 5) Write prices.json
    result = {"generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
              "prices": dict(sorted(prices.items())),
              "missing": sorted(missing),
              "fx": fx}
    with open(PRICES_FILE, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=1, ensure_ascii=False)

    # 6) Append to history/YYYY.csv (one row per date+id, re-runs replace instead of duplicate)
    os.makedirs("history", exist_ok=True)
    rows = pd.DataFrame(history_rows, columns=["date", "id", "close"])
    for y, new in rows.groupby(rows["date"].str[:4]):     # file = year of the close date
        path = f"history/{y}.csv"
        if os.path.exists(path):
            new = pd.concat([pd.read_csv(path, dtype={"id": str}), new])
        new = new.drop_duplicates(["date", "id"], keep="last").sort_values(["date", "id"])
        new.to_csv(path, index=False)

    fresh = len(prices) - sum(1 for p in prices.values() if p.get("stale"))
    print(f"Priced: {fresh} | missing: {len(missing)} -> {PRICES_FILE}")


if __name__ == "__main__":
    main()
