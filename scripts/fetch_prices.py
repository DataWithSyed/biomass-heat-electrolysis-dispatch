"""Fetch DE-LU day-ahead prices (Energy-Charts, CC BY 4.0) into data/.

Default window: last ~365 days ending yesterday. Re-run when the cache goes stale.
Attribution: Energy-Charts.info (Fraunhofer ISE); source Bundesnetzagentur | SMARD.de.
"""
from __future__ import annotations
import sys
from pathlib import Path
from datetime import date, timedelta

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from bhed.prices import fetch_da_prices, ATTRIBUTION  # noqa: E402

END = (date.today() - timedelta(days=1)).isoformat()
START = (date.today() - timedelta(days=366)).isoformat()
OUT = ROOT / "data" / "de_lu_da_hourly.csv.gz"

if __name__ == "__main__":
    print(ATTRIBUTION)
    print(f"fetching {START} .. {END}")
    s = fetch_da_prices(START, END, OUT)
    print(f"wrote {OUT} ({len(s)} hours, mean {s.mean():.1f} EUR/MWh)")
