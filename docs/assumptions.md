# Assumptions and limitations (electrolysis dispatch v0.1)

Labelled A-D1… for this repo. Plant-model assumptions A1–A23 still apply via the
dependency `biomass-heat-plant-model`.

| ID | Item | Value / setting | Notes |
|---|---|---|---|
| A-D1 | Process duty | Constant 10 MW heat, flue exit 1000 degC | Matches plant-model design point; no load profile yet (scenarios repo) |
| A-D2 | Configs | `oxy_partial`, `oxy_full`, `oxy_none_elec` | All use electrolyser O2; air / ASU-only chains have no dispatchable el load of interest |
| A-D3 | Electrolyser capacity (base) | 1.0 × design-point continuous rating | Oversizing swept at 1.25 / 1.5 / 2.0 × for `oxy_full` / O3 |
| A-D4 | Specific energy | 55 kWh/kg H2 (plant model) | System incl. BoP; engineering assumption |
| A-D5 | Storage | Ideal H2 and O2 buffers, sized in hours of design demand; start at 50 % SOC | No boil-off, no compression energy in the LP (plant simulate still books storage charge energy if configured) |
| A-D6 | Default storage | 24 h of design H2 and O2 demand | Swept 0–48 h for `oxy_full` / O3 |
| A-D7 | Prices | Hourly DE-LU day-ahead, Energy-Charts API (CC BY 4.0; source SMARD.de) | ~365 days ending 2026-10-30 in the committed cache; script re-fetches |
| A-D8 | O2 threshold (O2 strategy) | Median of the price series | Simple heuristic, not optimised |
| A-D9 | O3 LP | Perfect-foresight HiGHS LP on electrolyser MW; free H2/O2 venting; hard demand via storage | Upper bound; ignores forecast error and imbalance |
| A-D10 | O4 rolling | 48 h look-ahead, commit 24 h; each window starts at 50 % SOC | No persistent SOC warm-start (v0.1 simplification) |
| A-D11 | Fixed plant load | Compression + blower (+ ASU if any) runs with heat duty; not shifted | Only electrolyser power is dispatchable |
| A-D12 | Scope | Electricity cost only (EUR/MWh_heat); no biomass fuel cost, no CAPEX, no O2 sales | LCOH follows in `biomass-heat-lcoh` |

## Limitations

* Constant heat demand; no part-load gasifier/methanation efficiency curve.
* Storage is energy-only (no pressure, no compressor schedule).
* O4 does not carry SOC between windows.
* Negative prices: electrolyser is happy to run (no curtailment constraint beyond capacity).
* Cached prices are redistributed under CC BY 4.0 with attribution; re-fetch for newer days.
