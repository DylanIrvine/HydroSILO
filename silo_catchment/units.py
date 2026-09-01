"""Convert a flow series to mm/d over the catchment.

mm/d is depth, so every conversion needs the catchment area. This is why the
tool computes and carries the area: it is what lets flow be compared with, and
modelled alongside, the catchment-average rainfall.

    m3/s -> mm/d : q * 86400 s/day * 1000 mm/m / (area_km2 * 1e6 m2/km2)
                 = q * 86.4 / area_km2
    ML/d -> mm/d : q * 1000 m3/ML / (area_km2 * 1e6 m2) * 1000 mm/m
                 = q / area_km2
    mm/d -> mm/d : unchanged
"""

from __future__ import annotations

import numpy as np

FLOW_UNITS = ("m3/s", "ML/d", "mm/d")


def to_mmd(values, unit: str, area_km2: float):
    """Return the flow in mm/d. values may be a scalar, array or Series."""
    if unit not in FLOW_UNITS:
        raise ValueError(f"Unknown flow unit '{unit}'. Use one of {FLOW_UNITS}.")
    if unit == "mm/d":
        return values
    if area_km2 is None or not np.isfinite(area_km2) or area_km2 <= 0:
        raise ValueError("A positive catchment area is needed to convert to mm/d.")
    if unit == "m3/s":
        return values * 86.4 / area_km2
    return values / area_km2          # ML/d
