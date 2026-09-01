"""The map of SILO grid cells used for the catchment average.

Marker size scales with each cell's weight, so it is visible at a glance which
cells carry most of the catchment. Returns a Matplotlib figure the caller can
show and save.
"""

from __future__ import annotations

import geopandas as gpd
import matplotlib
import pandas as pd

matplotlib.use("Agg")            # no display needed on a server
import matplotlib.pyplot as plt  # noqa: E402

from .catchment import OUTPUT_EPSG


def sampling_map(catchment: gpd.GeoDataFrame, points: pd.DataFrame,
                 title: str = "SILO grid cells used for catchment averaging"):
    """Draw the catchment outline and the weighted grid cells over it."""
    outline = catchment.to_crs(epsg=OUTPUT_EPSG)
    cells = gpd.GeoDataFrame(
        points.copy(),
        geometry=gpd.points_from_xy(points["longitude"], points["latitude"]),
        crs=f"EPSG:{OUTPUT_EPSG}",
    )

    figure, axis = plt.subplots(figsize=(8, 8))
    outline.plot(ax=axis, color="#e5e5e5", edgecolor="#333333")
    largest = cells["weight"].max()
    sizes = 20 + 80 * cells["weight"] / largest if largest > 0 else 30
    cells.plot(ax=axis, color="#b03070", edgecolor="white", markersize=sizes)

    axis.set_title(title)
    axis.set_xlabel("Longitude")
    axis.set_ylabel("Latitude")
    axis.set_aspect("equal")
    figure.tight_layout()
    return figure
