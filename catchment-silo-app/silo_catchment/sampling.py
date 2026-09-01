"""Turn a catchment polygon into a small set of weighted SILO grid cells.

The catchment is sampled with points that are uniform by ground area (sampling
happens in Albers), each point is snapped to the 0.05 degree SILO grid, and
repeated cells are collapsed to weights. So a catchment is represented by the
unique grid cells that fall in it, weighted by how much of its area each covers,
and each cell is downloaded once.
"""

from __future__ import annotations

import math
import random

import geopandas as gpd
import pandas as pd
from shapely.geometry import Point

from .catchment import AREA_EPSG, OUTPUT_EPSG


def choose_number_of_points(area_km2: float, area_per_point_km2: float = 25.0,
                            min_points: int = 10, max_points: int = 80) -> int:
    """Sample count from area, held between a floor and a ceiling."""
    if area_per_point_km2 <= 0:
        raise ValueError("area_per_point_km2 must be greater than zero.")
    if min_points < 1 or max_points < min_points:
        raise ValueError("Require 1 <= min_points <= max_points.")
    area_based = math.ceil(area_km2 / area_per_point_km2)
    return max(min_points, min(max_points, area_based))


def snap_to_silo_grid(value: float, grid_degrees: float = 0.05) -> float:
    """Snap a coordinate to the nearest SILO grid line (0.05 deg by default)."""
    return round(round(value / grid_degrees) * grid_degrees, 2)


def generate_weighted_points(polygon_equal_area, number_of_samples: int,
                             seed: int = 137, grid_degrees: float = 0.05) -> pd.DataFrame:
    """Sample the polygon and aggregate samples that fall in the same grid cell.

    Returns one row per unique grid cell with a latitude, longitude, sample
    count and weight (its share of all samples). Weights sum to one.
    """
    generator = random.Random(seed)
    minx, miny, maxx, maxy = polygon_equal_area.bounds
    sampled: list[Point] = []
    attempts = 0
    max_attempts = max(10_000, number_of_samples * 10_000)

    while len(sampled) < number_of_samples:
        attempts += 1
        if attempts > max_attempts:
            raise RuntimeError(
                "Could not place enough sample points inside the catchment. "
                "The geometry may be invalid or unusually narrow."
            )
        candidate = Point(generator.uniform(minx, maxx),
                          generator.uniform(miny, maxy))
        if polygon_equal_area.covers(candidate):
            sampled.append(candidate)

    in_latlon = gpd.GeoDataFrame(
        {"sample_number": range(1, number_of_samples + 1)},
        geometry=sampled,
        crs=f"EPSG:{AREA_EPSG}",
    ).to_crs(epsg=OUTPUT_EPSG)

    snapped = pd.DataFrame({
        "latitude": [snap_to_silo_grid(p.y, grid_degrees) for p in in_latlon.geometry],
        "longitude": [snap_to_silo_grid(p.x, grid_degrees) for p in in_latlon.geometry],
    })

    unique = (snapped.groupby(["latitude", "longitude"], as_index=False)
              .size().rename(columns={"size": "sample_count"}))
    unique["weight"] = unique["sample_count"] / number_of_samples
    unique = unique.sort_values(["latitude", "longitude"],
                                ascending=[False, True]).reset_index(drop=True)
    unique.insert(0, "point_id", range(1, len(unique) + 1))
    return unique
