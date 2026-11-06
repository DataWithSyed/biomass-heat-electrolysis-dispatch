"""Design-point demands from the biomass-heat plant model (10 MW / 1000 degC)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable

from biomass_heat import Plant


CONFIGS = ("oxy_partial", "oxy_full", "oxy_none_elec")


@dataclass(frozen=True)
class DesignPoint:
    """Steady-state rates used to size electrolyser and storage for dispatch."""

    config: str
    heat_mw: float
    t_process_c: float
    el_mw: float                 # total plant electricity at design point
    el_electrolyser_mw: float    # electrolyser share (dispatchable)
    el_fixed_mw: float           # compression + blower (+ ASU if any); not shifted
    h2_need_kg_h: float
    o2_need_kg_h: float
    h2_kg_per_mwh: float
    electricity_mwh_per_mwh: float
    specific_energy_kwh_per_kg: float

    @property
    def h2_need_mol_s(self) -> float:
        return self.h2_need_kg_h / 3600.0 / 2.016e-3  # kg/h -> mol/s

    @property
    def o2_need_mol_s(self) -> float:
        return self.o2_need_kg_h / 3600.0 / 31.998e-3

    def h2_from_power_mol_s(self, power_w: float) -> float:
        kg_s = power_w / (self.specific_energy_kwh_per_kg * 3.6e6)
        return kg_s * 1000 / 2.016

    def power_for_h2_w(self, h2_mol_s: float) -> float:
        kg_s = h2_mol_s * 2.016 / 1000
        return kg_s * self.specific_energy_kwh_per_kg * 3.6e6


def design_point(config: str, heat_mw: float = 10.0,
                 t_process_c: float = 1000.0) -> DesignPoint:
    plant = Plant(config)
    dp = plant.design_point(heat_mw * 1e6, t_process_c + 273.15)
    el_fixed = (dp["el_compression_MW"] + dp["el_blower_MW"] + dp["el_asu_MW"])
    return DesignPoint(
        config=config,
        heat_mw=heat_mw,
        t_process_c=t_process_c,
        el_mw=dp["electricity_MW"],
        el_electrolyser_mw=dp["el_electrolyser_MW"],
        el_fixed_mw=el_fixed,
        h2_need_kg_h=dp["h2_kg_h"],
        o2_need_kg_h=dp["o2_demand_kg_h"],
        h2_kg_per_mwh=dp["h2_kg_per_MWh"],
        electricity_mwh_per_mwh=dp["electricity_MWh_per_MWh"],
        specific_energy_kwh_per_kg=plant.electrolyser.p.specific_energy_kwh_per_kg,
    )


def design_points(configs: Iterable[str] = CONFIGS, **kw) -> Dict[str, DesignPoint]:
    return {c: design_point(c, **kw) for c in configs}
