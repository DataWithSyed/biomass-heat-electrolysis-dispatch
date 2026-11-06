"""Electrolyser operating strategies O1-O4 and a thin runner on top of the plant model."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Sequence

import numpy as np
import pandas as pd
from scipy.optimize import linprog
from scipy.sparse import lil_matrix, csr_matrix

from biomass_heat import GasStorage, Plant, FollowDemand, PriceThreshold

from .design import DesignPoint


@dataclass
class FixedSchedule:
    """Feed a pre-computed electrolyser power schedule [W] into Plant.simulate."""

    power_w: Sequence[float]

    def electrolyser_power(self, t, plant, h2_need_mol_s, o2_need_mol_s, price,
                           h2_storage, o2_storage):
        return max(0.0, float(self.power_w[t % len(self.power_w)]))


@dataclass
class FollowDemandSchedule:
    """O1: electrolyser tracks the instantaneous H2 (or O2-driven) demand."""

    name: str = "O1_follow_demand"

    def strategy_obj(self, design: DesignPoint, capacity_w: float):
        return FollowDemand()


@dataclass
class PriceThresholdSchedule:
    """O2: run at capacity when price <= threshold, else draw from storage."""

    threshold_eur_mwh: float
    name: str = "O2_price_threshold"

    def strategy_obj(self, design: DesignPoint, capacity_w: float):
        return PriceThreshold(threshold_eur_mwh=self.threshold_eur_mwh,
                              capacity_W=capacity_w)


def _lp_schedule(prices: np.ndarray, design: DesignPoint, capacity_w: float,
                 h2_cap_mol: float, o2_cap_mol: float,
                 s0_h_frac: float = 0.5, s0_o_frac: float = 0.5,
                 return_soc: bool = False):
    """Minimise electrolyser electricity cost with perfect foresight (HiGHS).

    Decision variable ``p[t]`` = electrolyser power [MW]. H2 (and O2) demand is met
    every hour from production + storage; storage is ideal (no losses). Terminal SOC is
    free within bounds. Requires ``capacity_w`` >= design continuous rating for long
    horizons (otherwise the LP is infeasible and we fall back to follow-demand).
    """
    n = len(prices)
    h2_need = float(design.h2_need_mol_s)
    o2_need = float(design.o2_need_mol_s)
    cap_mw = float(capacity_w) / 1e6
    h2_per_mw = float(design.h2_from_power_mol_s(1e6))
    dt = 3600.0
    h2_cap = max(float(h2_cap_mol), 0.0)
    o2_cap = max(float(o2_cap_mol), 0.0)
    s0_h = float(s0_h_frac) * h2_cap
    s0_o = float(s0_o_frac) * o2_cap

    # Variables: p[0:n], sh[0:n+1], so[0:n+1], vent_h2[0:n], vent_o2[0:n]
    # Free venting matches the plant model (spill / O2 vent) and keeps the LP feasible
    # when co-product O2 would otherwise overfill storage during cheap-hour overproduction.
    n_p, n_sh, n_so, n_vh, n_vo = n, n + 1, n + 1, n, n
    N = n_p + n_sh + n_so + n_vh + n_vo
    i_sh = n_p
    i_so = n_p + n_sh
    i_vh = n_p + n_sh + n_so
    i_vo = i_vh + n_vh
    P = slice(0, n_p)

    c = np.zeros(N)
    c[P] = np.asarray(prices, dtype=float)   # EUR per MW over 1 h = EUR/MWh * MW

    # Equality: storage dynamics + initial SOC
    # sh[t+1] - sh[t] - h2_per_mw*dt * p[t] + vent_h2*dt = -h2_need*dt
    # so[t+1] - so[t] - 0.5*h2_per_mw*dt * p[t] + vent_o2*dt = -o2_need*dt
    n_eq = 2 + 2 * n
    Aeq = lil_matrix((n_eq, N))
    beq = np.zeros(n_eq)
    r = 0
    Aeq[r, i_sh + 0] = 1.0; beq[r] = s0_h; r += 1
    Aeq[r, i_so + 0] = 1.0; beq[r] = s0_o; r += 1
    for t in range(n):
        Aeq[r, i_sh + t + 1] = 1.0
        Aeq[r, i_sh + t] = -1.0
        Aeq[r, t] = -h2_per_mw * dt
        Aeq[r, i_vh + t] = dt
        beq[r] = -h2_need * dt
        r += 1
    for t in range(n):
        Aeq[r, i_so + t + 1] = 1.0
        Aeq[r, i_so + t] = -1.0
        Aeq[r, t] = -0.5 * h2_per_mw * dt
        Aeq[r, i_vo + t] = dt
        beq[r] = -o2_need * dt
        r += 1

    bounds = ([(0.0, cap_mw)] * n_p
              + [(0.0, max(h2_cap, 1e-9))] * n_sh
              + [(0.0, max(o2_cap, 1e-9))] * n_so
              + [(0.0, None)] * n_vh
              + [(0.0, None)] * n_vo)

    res = linprog(c, A_eq=csr_matrix(Aeq), b_eq=beq, bounds=bounds, method="highs")
    if not res.success:
        # Infeasible (e.g. capacity below continuous rating with empty storage): follow demand
        need_mw = min(cap_mw, design.el_electrolyser_mw)
        power = np.full(n, need_mw * 1e6, dtype=float)
        if return_soc:
            return power, s0_h_frac, s0_o_frac
        return power
    power_mw = np.asarray(res.x[P], dtype=float)
    power_mw = np.clip(power_mw, 0.0, cap_mw)
    power = power_mw * 1e6
    if return_soc:
        # SOC after full window (caller may truncate to commit_h and re-integrate)
        sh_end = float(res.x[i_sh + n])
        so_end = float(res.x[i_so + n])
        return power, (sh_end / h2_cap if h2_cap > 0 else 0.0), (so_end / o2_cap if o2_cap > 0 else 0.0)
    return power


@dataclass
class PerfectForesightLP:
    """O3: single-horizon LP over the full price series (upper bound)."""

    name: str = "O3_perfect_foresight"

    def schedule(self, prices: np.ndarray, design: DesignPoint, capacity_w: float,
                 h2_cap_mol: float, o2_cap_mol: float) -> np.ndarray:
        return _lp_schedule(prices, design, capacity_w, h2_cap_mol, o2_cap_mol)


@dataclass
class RollingDayAhead:
    """O4: each day optimise on a look-ahead window, commit 24 h, roll forward.

    Storage SOC is carried between windows (integrated on the committed hours).
    """

    look_ahead_h: int = 48
    commit_h: int = 24
    name: str = "O4_rolling_day_ahead"

    def schedule(self, prices: np.ndarray, design: DesignPoint, capacity_w: float,
                 h2_cap_mol: float, o2_cap_mol: float) -> np.ndarray:
        n = len(prices)
        out = np.zeros(n)
        s0_h, s0_o = 0.5, 0.5
        h2_need = design.h2_need_mol_s
        dt = 3600.0
        h2_level = s0_h * h2_cap_mol
        o2_level = s0_o * o2_cap_mol
        t0 = 0
        while t0 < n:
            H = min(self.look_ahead_h, n - t0)
            sh_frac = (h2_level / h2_cap_mol) if h2_cap_mol > 0 else 0.0
            so_frac = (o2_level / o2_cap_mol) if o2_cap_mol > 0 else 0.0
            sched = _lp_schedule(prices[t0:t0 + H], design, capacity_w, h2_cap_mol, o2_cap_mol,
                                 s0_h_frac=sh_frac, s0_o_frac=so_frac)
            k = min(self.commit_h, n - t0)
            out[t0:t0 + k] = sched[:k]
            # integrate committed hours on ideal storage (with free venting at bounds)
            for i in range(k):
                h2_prod = design.h2_from_power_mol_s(out[t0 + i])
                o2_prod = h2_prod * 0.5
                h2_level = min(max(h2_level + (h2_prod - h2_need) * dt, 0.0), max(h2_cap_mol, 0.0))
                o2_level = min(max(o2_level + (o2_prod - design.o2_need_mol_s) * dt, 0.0), max(o2_cap_mol, 0.0))
            t0 += k
        return out




def run_strategy(config: str, design: DesignPoint, prices: Sequence[float],
                 strategy_name: str, capacity_w: float,
                 h2_cap_mol: float, o2_cap_mol: float,
                 threshold_eur_mwh: Optional[float] = None,
                 heat_mw: float = 10.0, t_process_c: float = 1000.0,
                 use_plant_simulate: bool = False) -> pd.DataFrame:
    """Run one strategy. Default: fast constant-duty settlement (see settle.py).

    Set ``use_plant_simulate=True`` to go through the full agent-based Plant.simulate
    (slower; useful for cross-checks).
    """
    if not use_plant_simulate:
        from .settle import settle_constant
        return settle_constant(design, prices, strategy_name, capacity_w, h2_cap_mol,
                               o2_cap_mol, threshold_eur_mwh=threshold_eur_mwh)

    n = len(prices)
    prices = list(map(float, prices))
    demand = [heat_mw * 1e6] * n
    plant = Plant(config)
    plant.electrolyser.p.capacity_W = capacity_w

    h2s = GasStorage("h2_storage", capacity_mol=max(h2_cap_mol, 0.0),
                     max_rate_mol_s=max(design.h2_need_mol_s * 4, 1.0),
                     soc0=0.5 if h2_cap_mol > 0 else 0.0)
    o2s = GasStorage("o2_storage", capacity_mol=max(o2_cap_mol, 0.0),
                     max_rate_mol_s=max(design.o2_need_mol_s * 4, 1.0),
                     soc0=0.5 if o2_cap_mol > 0 else 0.0)

    if strategy_name == "O1_follow_demand":
        strat = FollowDemand()
    elif strategy_name == "O2_price_threshold":
        thr = threshold_eur_mwh if threshold_eur_mwh is not None else float(np.median(prices))
        strat = PriceThreshold(threshold_eur_mwh=thr, capacity_W=capacity_w)
    elif strategy_name in ("O3_perfect_foresight", "O4_rolling_day_ahead"):
        arr = np.asarray(prices, dtype=float)
        if strategy_name == "O3_perfect_foresight":
            power = PerfectForesightLP().schedule(arr, design, capacity_w, h2_cap_mol, o2_cap_mol)
        else:
            power = RollingDayAhead().schedule(arr, design, capacity_w, h2_cap_mol, o2_cap_mol)
        strat = FixedSchedule(power_w=power)
    else:
        raise ValueError(f"unknown strategy {strategy_name}")

    return plant.simulate(demand, prices, T_process=t_process_c + 273.15,
                          strategy=strat, h2_storage=h2s, o2_storage=o2s)


