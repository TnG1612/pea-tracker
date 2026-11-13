"""
build_yahoo_map.py - find the Yahoo Finance ticker for every asset in tickers.csv.

Run it once (and again when you add assets):   python build_yahoo_map.py
It writes yahoo_map.csv. Rows with status "check" or "unmapped" need a human look.
"""
import csv
from datetime import date, timedelta

import yfinance as yf

# The currency symbols used in tickers.csv -> ISO codes used by Yahoo
CURRENCY = {"€": "EUR", "EUR": "EUR", "$": "USD", "£": "GBP", "CHF": "CHF", "SEK": "SEK",
            "DKK": "DKK", "¥": "JPY", "KRW": "KRW", "HK$": "HKD"}
# Exchanges we prefer for ETFs, best first (Yahoo codes: Paris, Amsterdam, Xetra, Milan, London)
PREFERRED = ["PAR", "AMS", "GER", "MIL", "LSE"]
SUFFIX_FOR = {"PAR": ".PA", "AMS": ".AS", "GER": ".DE", "MIL": ".MI", "LSE": ".L"}


def isin_search(isin):
    """Ask Yahoo which tickers belong to this ISIN, sorted by our preferred exchanges."""
    try:
        quotes = yf.Search(isin, max_results=10).quotes
    except Exception:
        return []
    quotes = [q for q in quotes if q.get("exchange") in PREFERRED]
    quotes.sort(key=lambda q: PREFERRED.index(q["exchange"]))
    return [q["symbol"] for q in quotes]


def check(symbol):
    """Return Yahoo's name/currency/last date for a ticker, or None if it has no recent prices."""
    try:
        t = yf.Ticker(symbol)
        hist = t.history(period="10d")
        if hist.empty:
            return None
        meta = t.history_metadata
        last = hist.index[-1].date()
        if last < date.today() - timedelta(days=10):   # stale = probably delisted
            return None
        return {"yahoo_name": meta.get("longName") or meta.get("shortName", ""),
                "yahoo_currency": meta.get("currency", ""),
                "exchange": meta.get("exchangeName", ""),
                "last_date": last.isoformat()}
    except Exception:
        return None


def candidates(row, from_isin):
    """List of tickers to try for one row, best guess first."""
    t = row["ticker_in_dashboard"].strip().replace("BRK.B", "BRK-B")  # Yahoo uses a dash
    out = []
    if t and ("." in t or row["type"] != "ETF"):
        out.append(t)                                    # already a full Yahoo ticker
    elif t:                                              # ETF code without exchange suffix
        out += [t + s for s in SUFFIX_FOR.values()]
    return out + [s for s in from_isin if s not in out]


rows = list(csv.DictReader(open("tickers.csv", encoding="utf-8")))
result = []
for row in rows:
    isin = row["isin"].strip()
    from_isin = isin_search(isin) if isin else []
    wanted_cur = CURRENCY.get(row["currency"].strip(), "")

    found = []                                           # every candidate that has data
    for sym in candidates(row, from_isin):
        info = check(sym)
        if info:
            found.append((sym, info))
            # stocks: first working ticker wins. ETFs: stop once the currency matches.
            if row["type"] != "ETF" or info["yahoo_currency"] == wanted_cur:
                break

    out = {"id": row["id"], "name": row["name"], "isin": isin, "yahoo_ticker": "",
           "yahoo_name": "", "yahoo_currency": "", "exchange": "", "last_date": "",
           "status": "unmapped", "note": ""}
    if found:
        # prefer a listing in the expected currency, else the first one that works
        sym, info = next(((s, i) for s, i in found if i["yahoo_currency"] == wanted_cur), found[0])
        out.update(info, yahoo_ticker=sym, status="ok")
        notes = []
        if isin and from_isin and sym not in from_isin:
            notes.append("ISIN search did not list this ticker")
        if wanted_cur and info["yahoo_currency"].upper() not in (wanted_cur, "GBP" if wanted_cur == "GBP" else ""):
            notes.append(f"currency {info['yahoo_currency']} vs expected {wanted_cur}")
        if notes:
            out.update(status="check", note="; ".join(notes))
    result.append(out)
    print(f"{out['status']:9} {row['id']:14} {out['yahoo_ticker']:12} {out['yahoo_currency']:4} {out['yahoo_name'][:45]}")

with open("yahoo_map.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=list(result[0].keys()))
    w.writeheader()
    w.writerows(result)

print("\nok:", sum(r["status"] == "ok" for r in result),
      "| check:", sum(r["status"] == "check" for r in result),
      "| unmapped:", sum(r["status"] == "unmapped" for r in result))
