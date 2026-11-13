"""
add_asset.py - add a new stock or ETF to the tracker.

  1) Find it:   python add_asset.py search "Take-Two"
     Lists Yahoo tickers that match, with name, exchange, currency and last price.
  2) Add it:    python add_asset.py add TTWO
     Checks the ticker really has recent prices, then adds one line to
     tickers.csv and yahoo_map.csv. Prints the new line as JSON.

Options for "add": --id (key used everywhere, default = ticker without suffix),
--pea yes|no (default no), --zone (e.g. "États-Unis", "France", "Europe").
"""
import argparse
import csv
import json
import re
import sys
from datetime import date, timedelta

import yfinance as yf

# Yahoo currency -> the symbol style used in tickers.csv
CUR_SYMBOL = {"EUR": "€", "USD": "$", "GBp": "£", "GBP": "£"}
# Yahoo country -> zone names used in the dashboard
ZONE = {"United States": "États-Unis", "France": "France", "United Kingdom": "Royaume-Uni",
        "Switzerland": "Suisse", "Japan": "Japon", "China": "Chine", "India": "Inde", "Canada": "Canada"}
EUROPE = {"Germany", "Netherlands", "Italy", "Spain", "Belgium", "Ireland", "Luxembourg", "Finland",
          "Denmark", "Sweden", "Austria", "Portugal", "Norway"}


def last_prices(symbol):
    """(info dict, last close, last date) or None if no recent data."""
    t = yf.Ticker(symbol)
    hist = t.history(period="10d")
    if hist.empty or hist.index[-1].date() < date.today() - timedelta(days=10):
        return None
    return t.history_metadata, float(hist["Close"].iloc[-1]), hist.index[-1].date().isoformat()


def search(query):
    out = []
    for q in yf.Search(query, max_results=8).quotes:
        if q.get("quoteType") not in ("EQUITY", "ETF"):
            continue
        r = last_prices(q["symbol"])
        if r:
            meta, close, day = r
            out.append({"symbol": q["symbol"], "name": q.get("longname") or q.get("shortname"),
                        "exchange": q.get("exchDisp"), "type": q["quoteType"],
                        "currency": meta.get("currency"), "last_close": round(close, 4), "date": day})
    print(json.dumps(out, indent=1, ensure_ascii=False))


def add(symbol, asset_id, pea, zone):
    r = last_prices(symbol)
    if not r:
        sys.exit(f"{symbol}: no recent prices on Yahoo - not added.")
    meta, close, day = r
    info = {}
    try:
        info = yf.Ticker(symbol).info
    except Exception:
        pass
    name = info.get("longName") or meta.get("longName") or meta.get("shortName") or symbol
    kind = "ETF" if (info.get("quoteType") or meta.get("instrumentType")) == "ETF" else "Action"
    country = info.get("country", "")
    zone = zone or ZONE.get(country) or ("Europe" if country in EUROPE else "Monde")
    asset_id = asset_id or re.sub(r"[^A-Z0-9]", "", symbol.split(".")[0].upper())
    isin = ""
    try:
        isin = yf.Ticker(symbol).isin or ""
    except Exception:
        pass
    isin = isin if re.fullmatch(r"[A-Z]{2}[A-Z0-9]{9}\d", isin) else ""

    rows = list(csv.DictReader(open("tickers.csv", encoding="utf-8")))
    if any(x["id"] == asset_id for x in rows):
        sys.exit(f"id {asset_id} already exists in tickers.csv - not added.")
    if any(x["yahoo_ticker"] == symbol for x in csv.DictReader(open("yahoo_map.csv", encoding="utf-8"))):
        sys.exit(f"{symbol} is already tracked - not added.")

    cur = meta.get("currency", "")
    new = {"id": asset_id, "name": name, "isin": isin, "ticker_in_dashboard": symbol,
           "alpha_vantage_symbol": "", "type": kind, "currency": CUR_SYMBOL.get(cur, cur),
           "pea": pea, "zone": zone}
    with open("tickers.csv", "a", newline="", encoding="utf-8") as f:
        csv.DictWriter(f, fieldnames=list(new)).writerow(new)
    with open("yahoo_map.csv", "a", newline="", encoding="utf-8") as f:
        csv.writer(f).writerow([asset_id, name, isin, symbol, meta.get("longName") or name, cur,
                                meta.get("exchangeName", ""), day, "ok", "added with add_asset.py"])
    print(json.dumps({**new, "sector_hint": info.get("sector", ""), "industry": info.get("industry", ""),
                      "last_close": round(close, 4), "date": day}, ensure_ascii=False))


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("action", choices=["search", "add"])
    p.add_argument("query")
    p.add_argument("--id", default="")
    p.add_argument("--pea", choices=["yes", "no"], default="no")
    p.add_argument("--zone", default="")
    a = p.parse_args()
    search(a.query) if a.action == "search" else add(a.query, a.id, a.pea, a.zone)
