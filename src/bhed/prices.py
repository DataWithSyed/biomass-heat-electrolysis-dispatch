"""DE-LU day-ahead electricity prices from the Energy-Charts API (Fraunhofer ISE).

Licence: CC BY 4.0. Price source: Bundesnetzagentur | SMARD.de, redistributed via
Energy-Charts.info. Attribution must be retained. SMARD.de is an alternative direct
source. The API is rate-limited (~2 requests/min); requests honour HTTP 429 Retry-After.
"""
from __future__ import annotations

import time
from pathlib import Path

import pandas as pd
import requests

API = "https://api.energy-charts.info"
ATTRIBUTION = (
    "Day-ahead prices (DE-LU): Energy-Charts.info (Fraunhofer ISE), CC BY 4.0; "
    "underlying source Bundesnetzagentur | SMARD.de."
)


def _get(endpoint: str, params: dict, max_tries: int = 12) -> dict:
    for _ in range(max_tries):
        r = requests.get(f"{API}/{endpoint}", params=params, timeout=120)
        if r.status_code == 429:
            wait = int(r.headers.get("Retry-After", "40")) + 2
            print(f"  429 on {endpoint}, waiting {wait}s")
            time.sleep(wait)
            continue
        r.raise_for_status()
        return r.json()
    raise RuntimeError(f"gave up on {endpoint} {params}")


def fetch_da_prices(start: str, end: str, out: Path | str | None = None) -> pd.Series:
    """Hourly DE-LU day-ahead prices [EUR/MWh], UTC index, fetched in ~90-day chunks."""
    chunks = []
    t0 = pd.Timestamp(start, tz="UTC")
    t1 = pd.Timestamp(end, tz="UTC")
    cur = t0
    while cur <= t1:
        nxt = min(cur + pd.Timedelta(days=90), t1)
        p = _get("price", {"bzn": "DE-LU",
                           "start": cur.strftime("%Y-%m-%d"),
                           "end": nxt.strftime("%Y-%m-%d")})
        s = pd.Series(p["price"],
                      index=pd.to_datetime(p["unix_seconds"], unit="s", utc=True),
                      name="price", dtype="float64")
        chunks.append(s.resample("1h").mean())
        cur = nxt + pd.Timedelta(days=1)
        time.sleep(1.0)  # be polite to the API
    out_s = pd.concat(chunks).sort_index()
    out_s = out_s[~out_s.index.duplicated()].dropna()
    out_s.index.name = "time_utc"
    if out is not None:
        out = Path(out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out_s.round(2).to_csv(out, compression="gzip" if str(out).endswith(".gz") else None)
    return out_s


def load_prices(path: Path | str) -> pd.Series:
    """Load a cached hourly price CSV (optionally gzipped)."""
    df = pd.read_csv(path, index_col=0, parse_dates=True)
    col = "price" if "price" in df.columns else df.columns[0]
    s = df[col].astype(float)
    s.index = pd.to_datetime(s.index, utc=True)
    s.name = "price"
    return s.dropna()
