"""Derived catchment-scale climate columns, added after spatial averaging.

Excess water uses Morton wet-environment areal PET, which is the more defensible
actual-evaporation surrogate at the catchment scale than reference-crop FAO56.
The aridity index keeps FAO56, the usual reference for P/PET. Everything here is
optional; the streamlined output drops these and keeps the primary variables.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

RAIN = "Rain (mm)"
FAO56 = "FAO56 PET (mm)"
MORTON_WET = "Morton wet-environment areal PET (mm)"

# Columns kept when the user asks for the streamlined output.
STREAMLINED_COLUMNS = [
    "Date",
    RAIN,
    FAO56,
    MORTON_WET,
    "Maximum temperature (degC)",
    "Minimum temperature (degC)",
]

WATER_YEAR_START_MONTH = 10   # October start, common in northern Australia


def add_derived_columns(climate: pd.DataFrame,
                        water_year_start_month: int = WATER_YEAR_START_MONTH) -> pd.DataFrame:
    """Add excess water, aridity, cumulative rainfall and related columns."""
    climate = climate.copy()
    rain = climate[RAIN]
    wet_pet = climate[MORTON_WET]
    fao = climate[FAO56]

    climate["Excess water (mm)"] = (rain - wet_pet).clip(lower=0)
    climate["Aridity index (P/PET)"] = (rain /  wet_pet).replace([np.inf, -np.inf], np.nan)

    climate["7-day cumulative rainfall (mm)"] = rain.rolling(7, min_periods=1).sum()
    climate["14-day cumulative rainfall (mm)"] = rain.rolling(14, min_periods=1).sum()
    climate["7-day cumulative excess water (mm)"] = (
        climate["Excess water (mm)"].rolling(7, min_periods=1).sum())
    climate["14-day cumulative excess water (mm)"] = (
        climate["Excess water (mm)"].rolling(14, min_periods=1).sum())

    month = climate["Date"].dt.month
    year = climate["Date"].dt.year
    start_year = year.where(month >= water_year_start_month, year - 1)
    water_year_start = pd.to_datetime(
        start_year.astype(str) + f"-{water_year_start_month:02d}-01")
    #climate["Day of water year"] = (climate["Date"] - water_year_start).dt.days + 1

    # A 30-day rolling rainfall z-score, not a gamma-fitted SPI.
    rolling_mean = rain.rolling(30, min_periods=30).mean()
    rolling_std = rain.rolling(30, min_periods=30).std()
    #climate["30-day rolling rainfall z-score"] = (
    #    (rain - rolling_mean) / rolling_std).replace([np.inf, -np.inf], np.nan)

    return climate
