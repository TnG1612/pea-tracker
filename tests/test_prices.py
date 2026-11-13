"""
Sanity checks on prices.json.   Run with:  python -m pytest
A failing test stops the GitHub workflow BEFORE it commits bad data.
"""
import csv
import json
import warnings
from datetime import date, datetime, timedelta

import pytest


@pytest.fixture(scope="module")
def data():
    # json.load raises an error if the file is not valid JSON -> test fails
    with open("prices.json", encoding="utf-8") as f:
        return json.load(f)


def fresh(data):
    """Prices fetched in this run (not the old 'stale' ones kept from before)."""
    return [p for p in data["prices"].values() if not p.get("stale")]


def test_structure(data):
    assert set(data) == {"generatedAt", "prices", "missing"}
    datetime.fromisoformat(data["generatedAt"])          # must be a real ISO time
    for asset_id, p in data["prices"].items():
        assert p["id"] == asset_id
        assert {"yahoo_ticker", "price", "currency", "chg1d", "chgYtd", "date"} <= set(p)


def test_every_id_is_accounted_for(data):
    ids = {r["id"] for r in csv.DictReader(open("tickers.csv", encoding="utf-8"))}
    found = set(data["prices"]) | set(data["missing"])
    assert ids <= found, f"ids neither priced nor missing: {ids - found}"


def test_no_price_zero_or_negative(data):
    bad = [p["id"] for p in data["prices"].values() if not p["price"] > 0]
    assert not bad, f"price <= 0 for {bad}"


def test_dates_are_recent_trading_days(data):
    oldest_ok = date.today() - timedelta(days=7)          # allows for weekends + holidays
    for p in fresh(data):
        d = date.fromisoformat(p["date"])
        assert d.weekday() < 5, f"{p['id']}: {d} is a weekend"
        assert oldest_ok <= d <= date.today(), f"{p['id']}: date {d} is not recent"


def test_flag_big_daily_moves(data):
    """A move above 40% in one day is rare: show a WARNING (not a failure), so you can check it."""
    big = {p["id"]: p["chg1d"] for p in fresh(data) if abs(p["chg1d"]) > 40}
    if big:
        warnings.warn(f"1-day move above 40%, please check: {big}")
