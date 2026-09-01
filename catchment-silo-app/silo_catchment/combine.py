"""Join catchment climate and daily flow onto one continuous daily calendar.

Every climate column is retained so the user can pick their own PET later. Flow
is kept in its original units and also added in mm/d, so the combined file is
ready to drop into a rainfall-runoff model that expects depth.
"""

from __future__ import annotations

import pandas as pd

from .derived import STREAMLINED_COLUMNS
from .units import to_mmd


def combine_climate_and_flow(climate: pd.DataFrame, daily_flow: pd.DataFrame,
                             area_km2: float, flow_unit: str,
                             streamlined: bool = False,
                             date_format: str = "%Y-%m-%d") -> pd.DataFrame:
    """Merge climate and flow by date across their combined span.

    climate has a datetime Date column and the SILO variables. daily_flow has
    Date and Value (in flow_unit). The result spans the earliest to latest date
    of either input, with gaps left blank. Date is written as a string using
    date_format.
    """
    climate = climate.copy()
    climate["Date"] = pd.to_datetime(climate["Date"]).dt.normalize()
    if climate["Date"].duplicated().any():
        raise ValueError("The climate data has more than one row for a date.")

    if streamlined:
        keep = [c for c in STREAMLINED_COLUMNS if c in climate.columns]
        climate = climate.loc[:, keep]

    flow = daily_flow.loc[:, ["Date", "Value"]].copy()
    flow["Date"] = pd.to_datetime(flow["Date"]).dt.normalize()
    if flow["Date"].duplicated().any():
        raise ValueError("The daily flow has more than one row for a date.")
    flow = flow.rename(columns={"Value": f"Flow ({flow_unit})"})
    flow["Flow (mm/d)"] = to_mmd(flow[f"Flow ({flow_unit})"], flow_unit, area_km2)

    start = min(climate["Date"].min(), flow["Date"].min())
    end = max(climate["Date"].max(), flow["Date"].max())
    calendar = pd.DataFrame({"Date": pd.date_range(start, end, freq="D")})

    combined = (calendar
                .merge(climate, on="Date", how="left", validate="one_to_one")
                .merge(flow, on="Date", how="left", validate="one_to_one"))
    combined["Date"] = combined["Date"].dt.strftime(date_format)
    return combined
