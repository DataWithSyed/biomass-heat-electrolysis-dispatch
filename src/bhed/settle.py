"""Fast hourly settlement for *constant* heat duty.

Reuses design-point H2/O2/fixed-electricity rates so we do not re-solve the gasifier
every hour. Results match Plant.simulate for constant demand (verified in tests).
"""
from __future__ import annotations

from typing import Sequence

import numpy as np
import pandas as pd

from biomass_heat import GasStorage, FollowDemand, PriceThreshold

from .design import DesignPoint
from .strategies import FixedSchedule, PerfectForesightLP, RollingDayAhead


def settle_constant(design: DesignPoint, prices: Sequence[float], strategy_name: str,
                    capacity_w: float, h2_cap_mol: float, o2_cap_mol: float,
                    threshold_eur_mwh: float | None = None) -> pd.DataFrame:
    prices = np.asarray(prices, dtype=float)
    n = len(prices)
    h2_need = design.h2_need_mol_s
    o2_need = design.o2_need_mol_s
    fixed_mw = design.el_fixed_mw
    dt = 3600.0

    h2s = GasStorage("h2_storage", capacity_mol=max(h2_cap_mol, 0.0),
                     max_rate_mol_s=max(h2_need * 4, 1.0),
                     soc0=0.5 if h2_cap_mol > 0 else 0.0)
    o2s = GasStorage("o2_storage", capacity_mol=max(o2_cap_mol, 0.0),
                     max_rate_mol_s=max(o2_need * 4, 1.0),
                     soc0=0.5 if o2_cap_mol > 0 else 0.0)
    h2s.reset(); o2s.reset()

    # Build power schedule [W]
    if strategy_name == "O1_follow_demand":
        # Match plant FollowDemand: power_for_h2(h2_need); capacity clip applied below
        need_w = design.power_for_h2_w(h2_need)
        power = np.full(n, min(need_w, capacity_w))
    elif strategy_name == "O2_price_threshold":
        thr = float(threshold_eur_mwh if threshold_eur_mwh is not None else np.median(prices))
        power = np.zeros(n)
        # emulate PriceThreshold hour by hour with live storage
        for t in range(n):
            if prices[t] <= thr:
                power[t] = capacity_w
            else:
                from_store = min(h2s.level / dt, h2_need, h2s.max_rate)
                power[t] = design.power_for_h2_w(h2_need - from_store)
            power[t] = min(power[t], capacity_w)
            h2_prod = design.h2_from_power_mol_s(power[t])
            o2_prod = h2_prod / 2.0
            h2s.exchange(h2_prod - h2_need, dt)
            o2s.exchange(o2_prod - o2_need, dt)
        # reset storages for the accounting pass below
        h2s.reset(); o2s.reset()
    elif strategy_name == "O3_perfect_foresight":
        power = PerfectForesightLP().schedule(prices, design, capacity_w, h2_cap_mol, o2_cap_mol)
    elif strategy_name == "O4_rolling_day_ahead":
        power = RollingDayAhead().schedule(prices, design, capacity_w, h2_cap_mol, o2_cap_mol)
    else:
        raise ValueError(strategy_name)

    rows = []
    for t in range(n):
        p_w = min(max(float(power[t]), 0.0), capacity_w)
        h2_prod = design.h2_from_power_mol_s(p_w)
        o2_prod = h2_prod / 2.0
        h2x = h2s.exchange(h2_prod - h2_need, dt)
        o2x = o2s.exchange(o2_prod - o2_need, dt)
        # ASU tops up O2 shortfall
        o2_short = max(0.0, -o2x["unserved_mol_s"])
        # ASU: 0.25 kWh/kg O2 (plant-model default) -> MW = (kg/s) * 0.25 / 1000
        asu_mw = (o2_short * 31.998e-3) * 0.25 / 1000.0
        el_mw = p_w / 1e6 + fixed_mw + asu_mw
        price = float(prices[t])
        rows.append({
            "t": t, "price_eur_mwh": price, "heat_MW": design.heat_mw,
            "biomass_MW": 0.0,  # not tracked in fast path
            "electrolyser_MW": p_w / 1e6, "asu_MW": asu_mw, "electricity_MW": el_mw,
            "h2_need_kg": h2_need * 2.016e-3 * dt,
            "h2_produced_kg": h2_prod * 2.016e-3 * dt,
            "h2_unserved_kg": max(0.0, -h2x["unserved_mol_s"]) * 2.016e-3 * dt,
            "h2_spill_kg": max(0.0, h2x["unserved_mol_s"]) * 2.016e-3 * dt,
            "h2_storage_kg": h2s.level * 2.016e-3,
            "o2_storage_kg": o2s.level * 31.998e-3,
            "o2_vent_kg": max(0.0, o2x["unserved_mol_s"]) * 31.998e-3 * dt,
            "electricity_cost_eur": el_mw * price,  # MW * EUR/MWh * 1 h
        })
    return pd.DataFrame(rows)
