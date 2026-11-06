"""Price-dependent electrolysis + H2/O2 storage dispatch for biomass process-heat chains."""
from .design import DesignPoint, design_points
from .metrics import summarise
from .prices import fetch_da_prices, load_prices
from .sizing import storage_hours_to_mol, sweep_storage
from .strategies import (
    FollowDemandSchedule,
    PriceThresholdSchedule,
    PerfectForesightLP,
    RollingDayAhead,
    FixedSchedule,
    run_strategy,
)

__version__ = "0.1.0"
__all__ = [
    "DesignPoint", "design_points", "summarise", "fetch_da_prices", "load_prices",
    "storage_hours_to_mol", "sweep_storage", "FollowDemandSchedule",
    "PriceThresholdSchedule", "PerfectForesightLP", "RollingDayAhead",
    "FixedSchedule", "run_strategy", "__version__",
]
