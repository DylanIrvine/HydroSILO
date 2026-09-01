"""Download SILO Data Drill point series and average them over a catchment.

SILO Data Drill is a gridded product served by the Queensland Government's Long
Paddock. The 'alldata' format returns one whitespace table of daily climate for
a single grid cell. We download each unique cell for the catchment and take the
weighted daily mean.
"""

from __future__ import annotations

import re
import time
import urllib.error
import urllib.parse
import urllib.request
from io import StringIO
from typing import Callable

import pandas as pd

SILO_API_URL = "https://www.longpaddock.qld.gov.au/cgi-bin/silo/DataDrillDataset.php"

# SILO 'alldata' short name -> descriptive column kept in the output.
SILO_COLUMNS = {
    "Rain": "Rain (mm)",
    "FAO56": "FAO56 PET (mm)",
    "Evap": "Pan evaporation (mm)",
    "Span": "Synthetic pan evaporation (mm)",
    "T.Max": "Maximum temperature (degC)",
    "T.Min": "Minimum temperature (degC)",
    "Mwet": "Morton wet-environment areal PET (mm)",
    "RHmaxT": "Relative humidity at Tmax (%)",
    "RHminT": "Relative humidity at Tmin (%)",
}


def parse_silo_alldata(data: bytes) -> pd.DataFrame:
    """Convert a SILO 'alldata' response into a daily DataFrame."""
    text = data.decode("utf-8", errors="replace")
    lines = text.splitlines()

    header_index = next(
        (i for i, line in enumerate(lines)
         if re.match(r"^\s*Date\s+Day\s+Date2\b", line)),
        None,
    )
    if header_index is None or header_index + 2 >= len(lines):
        preview = "\n".join(lines[:20])
        raise ValueError(f"SILO returned an unrecognised response:\n{preview}")

    column_names = re.split(r"\s+", lines[header_index].strip())
    body = "\n".join(lines[header_index + 2:])
    raw = pd.read_csv(StringIO(body), sep=r"\s+", names=column_names,
                      header=None, engine="python")

    numeric_date = pd.to_numeric(raw["Date"], errors="coerce")
    raw = raw.loc[numeric_date.notna()].copy()
    raw["Date"] = pd.to_datetime(
        numeric_date.loc[numeric_date.notna()].astype("int64").astype(str),
        format="%Y%m%d",
    )

    missing = [c for c in SILO_COLUMNS if c not in raw.columns]
    if missing:
        raise ValueError(f"SILO response is missing columns: {', '.join(missing)}")

    out = pd.DataFrame({"Date": raw["Date"]})
    for source, destination in SILO_COLUMNS.items():
        out[destination] = pd.to_numeric(raw[source], errors="coerce")
    return out.reset_index(drop=True)


def download_silo_point(latitude: float, longitude: float, start: str, end: str,
                        email: str, timeout: int = 180, max_attempts: int = 3) -> pd.DataFrame:
    """Download one SILO grid cell for the date range, with retries.

    start and end are 'yyyymmdd' strings. email is passed as the SILO username
    per their API; it is used only for this request.
    """
    parameters = {
        "format": "alldata",
        "lat": f"{latitude:.2f}",
        "lon": f"{longitude:.2f}",
        "start": start,
        "finish": end,
        "username": email,
        "password": "apirequest",
        "comment": "catchment",
    }
    url = SILO_API_URL + "?" + urllib.parse.urlencode(parameters)
    request = urllib.request.Request(url, headers={"User-Agent": "CatchmentSILO-app"})

    for attempt in range(1, max_attempts + 1):
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return parse_silo_alldata(response.read())
        except (urllib.error.URLError, TimeoutError, ValueError) as error:
            if attempt == max_attempts:
                raise RuntimeError(
                    f"SILO download failed at {latitude:.2f}, {longitude:.2f} "
                    f"after {attempt} attempts: {error}"
                ) from error
            time.sleep(2 ** (attempt - 1))

    raise RuntimeError("Unexpected end of the SILO retry loop.")


def download_weighted_average(points: pd.DataFrame, start: str, end: str, email: str,
                              progress: Callable[[int, int, float, float], None] | None = None,
                              pause_seconds: float = 0.5, **download_kwargs) -> pd.DataFrame:
    """Download each unique cell and return the weighted daily mean climate.

    progress, if given, is called as progress(done, total, lat, lon) before each
    cell so a UI can show a bar. Weights need not sum to one; the mean divides by
    the total weight used.
    """
    weighted_sum: pd.DataFrame | None = None
    reference_index: pd.DatetimeIndex | None = None
    total_weight = 0.0
    total = len(points)

    for number, row in enumerate(points.itertuples(index=False), start=1):
        if progress is not None:
            progress(number, total, row.latitude, row.longitude)

        climate = download_silo_point(row.latitude, row.longitude, start, end,
                                      email, **download_kwargs).set_index("Date")

        if reference_index is None:
            reference_index = climate.index
            weighted_sum = climate * row.weight
        else:
            climate = climate.reindex(reference_index)
            if climate.isna().all(axis=1).any():
                raise ValueError(
                    "A SILO cell returned a different date range from the others."
                )
            weighted_sum = weighted_sum.add(climate * row.weight, fill_value=0)

        total_weight += row.weight
        if pause_seconds > 0:
            time.sleep(pause_seconds)

    if weighted_sum is None or total_weight <= 0:
        raise ValueError("No SILO data were downloaded.")

    return (weighted_sum / total_weight).reset_index()
