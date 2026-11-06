"""Summary metrics: electricity cost EUR/MWh_heat, full-load hours, storage use."""
from __future__ import annotations

import pandas as pd


def summarise(df: pd.DataFrame, capacity_w: float, heat_mw: float = 10.0) -> dict:
    heat_mwh = heat_mw * len(df)  # constant demand, 1 h steps
    el_mwh = float(df["electricity_MW"].sum())
    el_cost = float(df["electricity_cost_eur"].sum())
    el_only = float(df["electrolyser_MW"].sum())
    flh = el_only / (capacity_w / 1e6) if capacity_w > 0 else 0.0
    return {
        "hours": len(df),
        "heat_mwh": heat_mwh,
        "electricity_mwh": el_mwh,
        "electrolyser_mwh": el_only,
        "electricity_cost_eur": el_cost,
        "eur_per_mwh_heat": el_cost / heat_mwh if heat_mwh else float("nan"),
        "mean_price_eur_mwh": float(df["price_eur_mwh"].mean()),
        "volume_weighted_price_eur_mwh": (
            float((df["electricity_MW"] * df["price_eur_mwh"]).sum() / el_mwh)
            if el_mwh > 0 else float("nan")
        ),
        "electrolyser_flh": flh,
        "h2_unserved_kg": float(df["h2_unserved_kg"].sum()),
        "h2_spill_kg": float(df["h2_spill_kg"].sum()),
        "o2_vent_kg": float(df["o2_vent_kg"].sum()),
        "mean_h2_storage_kg": float(df["h2_storage_kg"].mean()),
        "mean_o2_storage_kg": float(df["o2_storage_kg"].mean()),
    }
