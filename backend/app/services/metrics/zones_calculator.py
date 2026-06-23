"""Power and heart-rate training zones derived from FTP / max HR."""
from __future__ import annotations

# Coggan 7-zone power model as % of FTP (upper bounds; Z7 unbounded).
POWER_ZONE_BOUNDS = {
    "Z1_recovery": (0.0, 0.55),
    "Z2_endurance": (0.56, 0.75),
    "Z3_tempo": (0.76, 0.90),
    "Z4_threshold": (0.91, 1.05),
    "Z5_vo2max": (1.06, 1.20),
    "Z6_anaerobic": (1.21, 1.50),
    "Z7_neuromuscular": (1.51, 99.0),
}

# % of max HR (5-zone).
HR_ZONE_BOUNDS = {
    "Z1": (0.50, 0.60),
    "Z2": (0.60, 0.70),
    "Z3": (0.70, 0.80),
    "Z4": (0.80, 0.90),
    "Z5": (0.90, 1.00),
}


def power_zones(ftp: float) -> dict[str, tuple[int, int]]:
    """Return absolute watt ranges for each power zone."""
    return {
        name: (round(lo * ftp), round(hi * ftp))
        for name, (lo, hi) in POWER_ZONE_BOUNDS.items()
    }


def hr_zones(max_hr: int) -> dict[str, tuple[int, int]]:
    return {
        name: (round(lo * max_hr), round(hi * max_hr))
        for name, (lo, hi) in HR_ZONE_BOUNDS.items()
    }
