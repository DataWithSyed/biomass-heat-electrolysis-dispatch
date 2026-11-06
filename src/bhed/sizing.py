"""Map storage duration (hours of design H2/O2 demand) to mol capacity."""
from __future__ import annotations

from typing import Dict, List, Sequence

import pandas as pd

from .design import DesignPoint
from .metrics import summarise
from .strategies import run_strategy


def storage_hours_to_mol(design: DesignPoint, hours: float) -> tuple[float, float]:
    """H2 and O2 storage capacities [mol] equal to ``hours`` of design-point demand."""
    return design.h2_need_mol_s * hours * 3600.0, design.o2_need_mol_s * hours * 3600.0


def sweep_storage(config: str, design: DesignPoint, prices: Sequence[float],
                  strategy_name: str, capacity_factor: float = 1.0,
                  hours_list: Sequence[float] = (0, 2, 6, 12, 24, 48),
                  threshold_eur_mwh: float | None = None) -> pd.DataFrame:
    """Run one strategy across a storage-duration sweep; return a metrics table."""
    cap_w = design.el_electrolyser_mw * 1e6 * capacity_factor
    rows: List[Dict] = []
    for h in hours_list:
        h2_mol, o2_mol = storage_hours_to_mol(design, float(h))
        df = run_strategy(config, design, prices, strategy_name, cap_w, h2_mol, o2_mol,
                          threshold_eur_mwh=threshold_eur_mwh, heat_mw=design.heat_mw,
                          t_process_c=design.t_process_c)
        m = summarise(df, cap_w, heat_mw=design.heat_mw)
        m.update(config=config, strategy=strategy_name, storage_h=float(h),
                 capacity_factor=capacity_factor,
                 electrolyser_mw=cap_w / 1e6,
                 h2_storage_kg=h2_mol * 2.016e-3,
                 o2_storage_kg=o2_mol * 31.998e-3)
        rows.append(m)
    return pd.DataFrame(rows)
