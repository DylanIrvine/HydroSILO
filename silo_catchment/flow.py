"""Read a flow file the user configures, and reduce it to one value per day.

Nothing about the file layout is assumed. The user says how many rows to skip,
which column is the date (or date-time) and which is the flow, what order the
date parts are in, and whether the data are sub-daily. Sub-daily data are
averaged to a daily mean over either a midnight or a 9am day.
"""

from __future__ import annotations

import pandas as pd

# Label shown to the user -> the pandas parsing flags for that part order. Using
# flags rather than strict format strings lets a time component (sub-daily data)
# be parsed automatically while still fixing the ambiguous day/month order.
DATE_FORMATS = {
    "dd/mm/yyyy": dict(dayfirst=True, yearfirst=False),
    "mm/dd/yyyy": dict(dayfirst=False, yearfirst=False),
    "yyyy/mm/dd": dict(dayfirst=False, yearfirst=True),
}

DELIMITERS = {
    "Comma ,": ",",
    "Tab": "\t",
    "Semicolon ;": ";",
    "Whitespace": r"\s+",
}

DAY_BOUNDARIES = {
    "Midnight to midnight": 0,
    "9am to 9am": 9,
}


def load_flow_table(source, skiprows: int = 0, delimiter: str = ",") -> pd.DataFrame:
    """Read the raw flow file into a DataFrame so its columns can be listed.

    source is a path or a file-like object. delimiter is a regex-capable
    separator (see DELIMITERS). Everything is read as text; typing happens later.
    """
    engine = "python" if delimiter == r"\s+" else "c"
    frame = pd.read_csv(source, skiprows=int(skiprows), sep=delimiter,
                        dtype=str, engine=engine)
    frame.columns = [str(c).strip().lstrip("\ufeff").lstrip("#").strip()
                     for c in frame.columns]
    if frame.empty or frame.shape[1] < 2:
        raise ValueError(
            "The flow file needs at least two columns after the skipped rows. "
            "Check the number of rows to skip and the delimiter."
        )
    return frame


def parse_flow(frame: pd.DataFrame, date_column: str, flow_column: str,
               date_format: str) -> pd.DataFrame:
    """Return a two-column frame of parsed Datetime and numeric Value."""
    if date_format not in DATE_FORMATS:
        raise ValueError(f"Unknown date format '{date_format}'.")
    if date_column not in frame.columns or flow_column not in frame.columns:
        raise ValueError("The chosen date or flow column is not in the file.")

    flags = DATE_FORMATS[date_format]
    stamp = frame[date_column].astype("string").str.strip()

    # Kisters / BoM Water Data Online timestamps carry a timezone offset, for
    # example 1953-03-02T09:00:00.000+09:30. Parsed as-is these become
    # timezone-aware and then cannot be merged or compared against the
    # timezone-naive SILO dates. Drop a trailing 'Z' or +HH:MM / -HH:MM offset
    # so the local wall-clock time is kept: the 9am stamp stays at 9am on its
    # own date. The date part is never at the end of the string, so this cannot
    # touch it.
    stamp = stamp.str.replace(r"\s*(?:Z|[+-]\d{2}:?\d{2})\s*$", "", regex=True)

    parsed = pd.to_datetime(stamp, errors="coerce", **flags)
    # Belt and braces: if anything still parsed as timezone-aware (an unusual
    # offset spelling), keep the local wall-clock time and drop the zone.
    if isinstance(parsed.dtype, pd.DatetimeTZDtype):
        parsed = parsed.dt.tz_localize(None)

    bad = parsed.isna() & stamp.notna() & (stamp != "")
    if bad.all():
        examples = stamp.loc[bad].dropna().unique()[:5].tolist()
        raise ValueError(
            f"None of the dates could be read as {date_format}. "
            f"Examples from the file: {examples}"
        )

    value = pd.to_numeric(frame[flow_column], errors="coerce")
    out = pd.DataFrame({"Datetime": parsed, "Value": value})
    return out.loc[out["Datetime"].notna()].reset_index(drop=True)


def to_daily_mean(parsed: pd.DataFrame, boundary_hour: int = 0) -> pd.DataFrame:
    """Reduce a parsed flow frame to one mean value per day.

    boundary_hour 0 groups by calendar date. boundary_hour 9 groups by the 24
    hours ending at 9am and labels each window by the date it ends on, matching
    the day-to-9am convention used for SILO and BoM rainfall. Daily input passes
    through unchanged under either boundary (the mean of one value is itself).
    """
    frame = parsed.dropna(subset=["Datetime"]).sort_values("Datetime")
    if frame.empty:
        raise ValueError("No valid timestamps remain after parsing.")

    if boundary_hour == 0:
        label = frame["Datetime"].dt.floor("D")
    else:
        offset = pd.Timedelta(hours=boundary_hour)
        window_start = (frame["Datetime"] - offset).dt.floor("D")
        # window [boundary on g, boundary on g+1) ends on g+1; label it g+1
        label = window_start + pd.Timedelta(days=1)

    grouped = frame.groupby(label)["Value"]
    daily = grouped.mean().reset_index()
    daily.columns = ["Date", "Value"]
    daily["n_obs"] = grouped.size().to_numpy()
    daily["Date"] = pd.to_datetime(daily["Date"]).dt.normalize()
    return daily
