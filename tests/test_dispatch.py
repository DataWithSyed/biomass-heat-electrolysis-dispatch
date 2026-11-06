"""Offline tests on the cached 14-day DE-LU price sample (no live API)."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]

from bhed.design import design_point
from bhed.metrics import summarise
from bhed.prices import load_prices, ATTRIBUTION
from bhed.sizing import storage_hours_to_mol, sweep_storage
from bhed.strategies import PerfectForesightLP, run_strategy


@pytest.fixture(scope="module")
def prices():
    return load_prices(ROOT / "data" / "de_lu_da_sample.csv.gz")


@pytest.fixture(scope="module")
def dp_full():
    return design_point("oxy_full")


def test_attribution_mentions_licence():
    assert "CC BY 4.0" in ATTRIBUTION
    assert "SMARD" in ATTRIBUTION


def test_design_point_matches_plant_model_headline(dp_full):
    assert abs(dp_full.el_electrolyser_mw - 23.75) < 0.5
    assert abs(dp_full.h2_kg_per_mwh - 43.2) < 0.5


def test_o1_zero_storage_has_no_unserved(prices, dp_full):
    cap = dp_full.el_electrolyser_mw * 1e6
    df = run_strategy("oxy_full", dp_full, prices.values, "O1_follow_demand",
                      cap, 0.0, 0.0, heat_mw=10.0)
    m = summarise(df, cap)
    assert m["h2_unserved_kg"] < 1e-6
    assert m["eur_per_mwh_heat"] > 0


def test_o3_beats_or_matches_o1_with_storage(prices, dp_full):
    cap = dp_full.el_electrolyser_mw * 1e6
    h2, o2 = storage_hours_to_mol(dp_full, 12.0)
    m1 = summarise(run_strategy("oxy_full", dp_full, prices.values, "O1_follow_demand",
                                cap, h2, o2), cap)
    m3 = summarise(run_strategy("oxy_full", dp_full, prices.values, "O3_perfect_foresight",
                                cap, h2, o2), cap)
    assert m3["eur_per_mwh_heat"] <= m1["eur_per_mwh_heat"] * 1.01 + 0.5
    assert m3["h2_unserved_kg"] < 1.0


def test_o2_threshold_runs(prices, dp_full):
    cap = dp_full.el_electrolyser_mw * 1e6
    h2, o2 = storage_hours_to_mol(dp_full, 6.0)
    thr = float(np.median(prices.values))
    df = run_strategy("oxy_full", dp_full, prices.values, "O2_price_threshold",
                      cap, h2, o2, threshold_eur_mwh=thr)
    assert len(df) == len(prices)
    assert df["electrolyser_MW"].max() <= cap / 1e6 + 1e-6


def test_o4_rolling_produces_schedule(prices):
    dp = design_point("oxy_partial")
    cap = dp.el_electrolyser_mw * 1e6
    h2, o2 = storage_hours_to_mol(dp, 6.0)
    df = run_strategy("oxy_partial", dp, prices.values, "O4_rolling_day_ahead",
                      cap, h2, o2)
    assert len(df) == len(prices)
    assert df["electrolyser_MW"].sum() > 0
    assert df["electrolyser_MW"].min() >= -1e-9


def test_storage_sweep_monotonic_cost_direction(prices, dp_full):
    sw = sweep_storage("oxy_full", dp_full, prices.values, "O3_perfect_foresight",
                       hours_list=(0, 6, 24))
    costs = sw["eur_per_mwh_heat"].values
    assert costs[-1] <= costs[0] * 1.01 + 1.0


def test_lp_respects_capacity(prices, dp_full):
    cap = dp_full.el_electrolyser_mw * 1e6 * 1.25
    h2, o2 = storage_hours_to_mol(dp_full, 24.0)
    power = PerfectForesightLP().schedule(prices.values, dp_full, cap, h2, o2)
    assert power.max() <= cap + 1.0
    assert power.min() >= -1e-6
    # with oversizing, should sometimes idle and sometimes hit capacity
    assert power.max() > 0.5 * cap


def test_fast_settle_matches_plant_simulate_o1(prices, dp_full):
    from bhed.strategies import run_strategy
    from bhed.sizing import storage_hours_to_mol
    from bhed.metrics import summarise
    cap = dp_full.el_electrolyser_mw * 1e6
    h2, o2 = storage_hours_to_mol(dp_full, 6.0)
    sample = prices.values[:72]
    fast = summarise(run_strategy("oxy_full", dp_full, sample, "O1_follow_demand",
                                  cap, h2, o2, use_plant_simulate=False), cap)
    slow = summarise(run_strategy("oxy_full", dp_full, sample, "O1_follow_demand",
                                  cap, h2, o2, use_plant_simulate=True), cap)
    assert abs(fast["eur_per_mwh_heat"] - slow["eur_per_mwh_heat"]) / max(slow["eur_per_mwh_heat"], 1) < 0.02
    assert abs(fast["electrolyser_mwh"] - slow["electrolyser_mwh"]) < 0.5
