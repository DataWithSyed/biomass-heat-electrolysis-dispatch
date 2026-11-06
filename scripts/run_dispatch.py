"""Run O1-O4 strategies for oxy_partial / oxy_full / oxy_none_elec and write results + figures."""
from __future__ import annotations
import json, sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from bhed.design import design_points, CONFIGS
from bhed.metrics import summarise
from bhed.prices import load_prices, ATTRIBUTION
from bhed.sizing import storage_hours_to_mol, sweep_storage
from bhed.strategies import run_strategy

RES, FIG = ROOT / "results", ROOT / "figures"
RES.mkdir(exist_ok=True); FIG.mkdir(exist_ok=True)

PRICES = load_prices(ROOT / "data" / "de_lu_da_hourly.csv.gz")
print(ATTRIBUTION)
print(f"prices: {PRICES.index.min()} .. {PRICES.index.max()}  n={len(PRICES)}  "
      f"mean={PRICES.mean():.1f} EUR/MWh")

DPS = design_points()
STORAGE_H = 24.0
THRESHOLD = float(PRICES.median())
STRATS = ["O1_follow_demand", "O2_price_threshold", "O3_perfect_foresight", "O4_rolling_day_ahead"]
# Base published case uses 1.5x electrolyser: at 1.0x there is almost no arbitrage headroom
CAPACITY_FACTOR = 1.5

rows = []
hourly_dir = RES / "hourly"; hourly_dir.mkdir(exist_ok=True)

for cfg, dp in DPS.items():
    cap_w = dp.el_electrolyser_mw * 1e6 * CAPACITY_FACTOR
    h2_mol, o2_mol = storage_hours_to_mol(dp, STORAGE_H)
    print(f"\n=== {cfg}: el={cap_w/1e6:.2f} MW ({CAPACITY_FACTOR}x), H2={dp.h2_need_kg_h:.1f} kg/h, "
          f"storage {STORAGE_H} h ===", flush=True)
    for name in STRATS:
        print(f"  {name} ...", flush=True)
        df = run_strategy(cfg, dp, PRICES.values, name, cap_w, h2_mol, o2_mol,
                          threshold_eur_mwh=THRESHOLD)
        m = summarise(df, cap_w, heat_mw=dp.heat_mw)
        m.update(config=cfg, strategy=name, storage_h=STORAGE_H,
                 capacity_factor=CAPACITY_FACTOR, electrolyser_mw=cap_w / 1e6,
                 threshold_eur_mwh=THRESHOLD if name.startswith("O2") else None,
                 h2_storage_kg=h2_mol * 2.016e-3, o2_storage_kg=o2_mol * 31.998e-3)
        rows.append(m)
        df.head(168).to_csv(hourly_dir / f"{cfg}_{name}_week1.csv", index=False)
        print(f"    EUR/MWh_heat={m['eur_per_mwh_heat']:.1f}  FLH={m['electrolyser_flh']:.0f}  "
              f"H2_unserved={m['h2_unserved_kg']:.1f} kg  VWAP={m['volume_weighted_price_eur_mwh']:.1f}",
              flush=True)

summary = pd.DataFrame(rows)
summary.to_csv(RES / "dispatch_summary.csv", index=False)
print("\n", summary[["config", "strategy", "eur_per_mwh_heat", "electrolyser_flh",
                     "volume_weighted_price_eur_mwh", "h2_unserved_kg"]].to_string(index=False))

# Reference: 1.0x follow-demand (no flexibility)
ref_rows = []
for cfg, dp in DPS.items():
    cap_w = dp.el_electrolyser_mw * 1e6
    df = run_strategy(cfg, dp, PRICES.values, "O1_follow_demand", cap_w, 0.0, 0.0)
    m = summarise(df, cap_w, heat_mw=dp.heat_mw)
    m.update(config=cfg, strategy="O1_follow_demand_1x_no_storage", capacity_factor=1.0, storage_h=0.0)
    ref_rows.append(m)
pd.DataFrame(ref_rows).to_csv(RES / "dispatch_reference_1x.csv", index=False)

print("\n=== storage sweep oxy_full / O3 @ 1.5x ===", flush=True)
sweep = sweep_storage("oxy_full", DPS["oxy_full"], PRICES.values, "O3_perfect_foresight",
                      capacity_factor=1.5, hours_list=(0, 2, 6, 12, 24, 48))
sweep.to_csv(RES / "storage_sweep_oxy_full_O3.csv", index=False)
print(sweep[["storage_h", "eur_per_mwh_heat", "electrolyser_flh"]].to_string(index=False))

print("\n=== capacity sweep oxy_full / O3 @ 24 h ===", flush=True)
cap_rows = []
for cf in (1.0, 1.25, 1.5, 2.0):
    h2_mol, o2_mol = storage_hours_to_mol(DPS["oxy_full"], 24.0)
    cap_w = DPS["oxy_full"].el_electrolyser_mw * 1e6 * cf
    df = run_strategy("oxy_full", DPS["oxy_full"], PRICES.values, "O3_perfect_foresight",
                      cap_w, h2_mol, o2_mol)
    m = summarise(df, cap_w, heat_mw=10.0)
    m.update(capacity_factor=cf, electrolyser_mw=cap_w / 1e6)
    cap_rows.append(m)
    print(f"  {cf}x -> {m['eur_per_mwh_heat']:.1f} EUR/MWh_heat, FLH={m['electrolyser_flh']:.0f}, "
          f"VWAP={m['volume_weighted_price_eur_mwh']:.1f}", flush=True)
pd.DataFrame(cap_rows).to_csv(RES / "capacity_sweep_oxy_full_O3.csv", index=False)

# Strategy comparison at 1.0x vs 1.5x for oxy_full
print("\n=== oxy_full strategy x capacity ===", flush=True)
cross = []
for cf in (1.0, 1.5):
    for name in STRATS:
        h2_mol, o2_mol = storage_hours_to_mol(DPS["oxy_full"], 24.0)
        cap_w = DPS["oxy_full"].el_electrolyser_mw * 1e6 * cf
        df = run_strategy("oxy_full", DPS["oxy_full"], PRICES.values, name, cap_w, h2_mol, o2_mol,
                          threshold_eur_mwh=THRESHOLD)
        m = summarise(df, cap_w, heat_mw=10.0)
        m.update(capacity_factor=cf, strategy=name)
        cross.append(m)
        print(f"  {cf}x {name}: {m['eur_per_mwh_heat']:.1f}  unserved={m['h2_unserved_kg']:.0f}", flush=True)
pd.DataFrame(cross).to_csv(RES / "oxy_full_strategy_x_capacity.csv", index=False)

# ---- figures
fig, ax = plt.subplots(1, 2, figsize=(11.5, 4.3))
pivot = summary.pivot(index="config", columns="strategy", values="eur_per_mwh_heat")
order = ["oxy_none_elec", "oxy_partial", "oxy_full"]
pivot = pivot.loc[[c for c in order if c in pivot.index], STRATS]
x = np.arange(len(pivot)); w = 0.18; colors = ["#4c9a6a", "#e07b39", "#1f5f8b", "#8c3a22"]
for i, col in enumerate(STRATS):
    ax[0].bar(x + (i - 1.5) * w, pivot[col].values, w, label=col.replace("_", " "), color=colors[i])
# reference 1x markers
ref = pd.DataFrame(ref_rows).set_index("config")
ax[0].scatter(x, [ref.loc[c, "eur_per_mwh_heat"] for c in pivot.index],
              marker="_", s=200, color="k", label="O1 at 1x, no storage", zorder=5)
ax[0].set_xticks(x); ax[0].set_xticklabels(pivot.index, rotation=15, ha="right")
ax[0].set_ylabel("Electricity cost (EUR / MWh_heat)")
ax[0].set_title(f"DE-LU DA, {STORAGE_H:.0f} h storage, {CAPACITY_FACTOR:.1f}× electrolyser")
ax[0].legend(fontsize=6.5); ax[0].grid(axis="y", alpha=0.3)

ax[1].plot(sweep.storage_h, sweep.eur_per_mwh_heat, "o-", color="#1f5f8b", label="EUR/MWh_heat")
ax1b = ax[1].twinx()
ax1b.plot(sweep.storage_h, sweep.electrolyser_flh, "s--", color="#e07b39", label="FLH")
ax[1].set_xlabel("H2/O2 storage (hours of design demand)")
ax[1].set_ylabel("EUR / MWh_heat"); ax1b.set_ylabel("Electrolyser full-load hours")
ax[1].set_title("Storage trade-off (oxy_full, O3, 1.5× el.)")
lines, labels = ax[1].get_legend_handles_labels()
lines2, labels2 = ax1b.get_legend_handles_labels()
ax[1].legend(lines + lines2, labels + labels2, fontsize=7)
fig.tight_layout()
fig.savefig(FIG / "01_dispatch_cost_and_storage.png", dpi=140)
plt.close()

# capacity sweep figure
capdf = pd.read_csv(RES / "capacity_sweep_oxy_full_O3.csv")
fig, ax = plt.subplots(1, 2, figsize=(10.5, 4.0))
ax[0].plot(capdf.capacity_factor, capdf.eur_per_mwh_heat, "o-", color="#1f5f8b")
ax[0].set_xlabel("Electrolyser capacity factor (× design)"); ax[0].set_ylabel("EUR / MWh_heat")
ax[0].set_title("Oversizing cuts electricity cost (oxy_full, O3, 24 h)")
ax[1].plot(capdf.capacity_factor, capdf.volume_weighted_price_eur_mwh, "o-", color="#e07b39",
           label="electrolyser VWAP")
ax[1].axhline(float(PRICES.mean()), color="#555", ls="--", label=f"mean DA {PRICES.mean():.0f}")
ax[1].set_xlabel("Electrolyser capacity factor"); ax[1].set_ylabel("EUR / MWh_el")
ax[1].set_title("Volume-weighted purchase price"); ax[1].legend(fontsize=7)
fig.tight_layout(); fig.savefig(FIG / "03_capacity_oversizing.png", dpi=140); plt.close()

# week 1 price vs load
fig, ax = plt.subplots(2, 1, figsize=(10, 5.5), sharex=True)
d1 = pd.read_csv(hourly_dir / "oxy_full_O1_follow_demand_week1.csv")
d3 = pd.read_csv(hourly_dir / "oxy_full_O3_perfect_foresight_week1.csv")
ax[0].plot(d1.t, d1.price_eur_mwh, color="#555", lw=1.0)
ax[0].axhline(THRESHOLD, color="#e07b39", ls="--", lw=0.8, label=f"O2 threshold {THRESHOLD:.0f}")
ax[0].set_ylabel("EUR/MWh"); ax[0].set_title("DE-LU day-ahead price (week 1)")
ax[0].legend(fontsize=7)
ax[1].plot(d1.t, d1.electrolyser_MW, label="O1 follow-demand", color="#4c9a6a", lw=1.2)
ax[1].plot(d3.t, d3.electrolyser_MW, label="O3 perfect foresight", color="#1f5f8b", lw=1.2)
ax[1].set_ylabel("Electrolyser MW"); ax[1].set_xlabel("Hour")
ax[1].set_title(f"oxy_full electrolyser load ({CAPACITY_FACTOR}× capacity, 24 h storage)")
ax[1].legend(fontsize=7)
fig.tight_layout(); fig.savefig(FIG / "02_price_vs_electrolyser_week.png", dpi=140); plt.close()

meta = dict(
    attribution=ATTRIBUTION,
    price_start=str(PRICES.index.min()), price_end=str(PRICES.index.max()),
    n_hours=int(len(PRICES)), mean_price_eur_mwh=float(PRICES.mean()),
    median_price_eur_mwh=float(PRICES.median()),
    storage_h_default=STORAGE_H, capacity_factor_default=CAPACITY_FACTOR,
    threshold_eur_mwh=THRESHOLD,
    design_points={k: dp.__dict__ for k, dp in DPS.items()},
)
json.dump(meta, open(RES / "run_meta.json", "w"), indent=2)
print("done -> results/, figures/")
