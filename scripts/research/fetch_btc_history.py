#!/usr/bin/env python3
"""
Fetch BTC/USDT OHLCV history from KuCoin's PUBLIC market data endpoint.
No API key needed. Saves to data/btc_usdt_1h.csv.

Usage:
python3 scripts/research/fetch_btc_history.py --days 120 --tf 1h
"""
from __future__ import annotations
import argparse
import csv
import os
import time
import urllib.request
import json
from pathlib import Path

KU_BASE = "https://api.kucoin.com"
TF_MAP = {
    "1m": ("1min", 60),
    "5m": ("5min", 300),
    "15m": ("15min", 900),
    "1h": ("1hour", 3600),
    "4h": ("4hour", 14400),
    "1d": ("1day", 86400),
}


def fetch_chunk(symbol: str, tf_name: str, start: int, end: int) -> list[list]:
    url = (
        f"{KU_BASE}/api/v1/market/candles"
        f"?type={tf_name}&symbol={symbol}&startAt={start}&endAt={end}"
    )
    req = urllib.request.Request(url, headers={"User-Agent": "kucoin-lane-research/1.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        body = json.loads(r.read())
    if body.get("code") != "200000":
        raise RuntimeError(f"KuCoin error: {body}")
    return body.get("data") or []


def fetch_history(symbol: str, tf: str, days: int) -> list[dict]:
    tf_name, tf_secs = TF_MAP[tf]
    end = int(time.time())
    start = end - days * 86400
    chunk_bars = 1400
    chunk_secs = chunk_bars * tf_secs
    rows: dict[int, list] = {}
    cur_end = end
    while cur_end > start:
        cur_start = max(start, cur_end - chunk_secs)
        chunk = fetch_chunk(symbol, tf_name, cur_start, cur_end)
        if not chunk:
            break
        for c in chunk:
            ts = int(c[0])
            rows[ts] = c
        oldest = min(int(c[0]) for c in chunk)
        cur_end = oldest - 1
        time.sleep(0.25)
    sorted_rows = [rows[k] for k in sorted(rows.keys())]
    out = []
    for c in sorted_rows:
        out.append(
            {
                "ts": int(c[0]),
                "open": float(c[1]),
                "close": float(c[2]),
                "high": float(c[3]),
                "low": float(c[4]),
                "volume": float(c[5]),
            }
        )
    return out


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--symbol", default="BTC-USDT")
    p.add_argument("--tf", default="1h", choices=list(TF_MAP.keys()))
    p.add_argument("--days", type=int, default=120)
    p.add_argument("--out", default=None)
    args = p.parse_args()

    out_path = Path(
        args.out
        or f"data/{args.symbol.lower().replace('-', '_')}_{args.tf}.csv"
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)

    print(f"Fetching {args.days}d of {args.symbol} {args.tf} from KuCoin...")
    bars = fetch_history(args.symbol, args.tf, args.days)
    print(f" → {len(bars)} bars fetched")
    if bars:
        first = bars[0]["ts"]
        last = bars[-1]["ts"]
        print(f" range: {first} → {last} ({(last-first)/86400:.1f} days)")

    with out_path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["ts", "open", "high", "low", "close", "volume"])
        w.writeheader()
        for b in bars:
            w.writerow(
                {
                    "ts": b["ts"],
                    "open": b["open"],
                    "high": b["high"],
                    "low": b["low"],
                    "close": b["close"],
                    "volume": b["volume"],
                }
            )
    print(f" saved → {out_path}")


if __name__ == "__main__":
    main()