"""Load a catchment boundary and reduce it to one polygon with a known area.

Accepts a zipped shapefile, a bare shapefile set, a GeoPackage or a GeoJSON.
Area and the point sampling are done in GDA94 / Australian Albers (EPSG:3577),
an equal-area projection in metres, so that areas are correct and sampling is
uniform by ground area rather than by degrees.
"""

from __future__ import annotations

import tempfile
import zipfile
from pathlib import Path

import geopandas as gpd

AREA_EPSG = 3577      # GDA94 / Australian Albers, equal area, metres
OUTPUT_EPSG = 4283    # GDA94 latitude/longitude, for the SILO request


def _find_single(folder: Path, suffix: str) -> Path:
    matches = sorted(folder.rglob(f"*{suffix}"))
    if not matches:
        raise FileNotFoundError(f"No {suffix} file was found in the upload.")
    if len(matches) > 1:
        names = ", ".join(p.name for p in matches)
        raise ValueError(
            f"The upload contains more than one {suffix} file ({names}). "
            "Please supply a single catchment."
        )
    return matches[0]


def load_geodataframe(path, extract_dir: Path | None = None) -> gpd.GeoDataFrame:
    """Read a catchment file into a GeoDataFrame.

    A .zip is extracted to a temporary folder and the single shapefile inside it
    is read. .shp, .gpkg and .geojson are read directly.
    """
    path = Path(path)
    suffix = path.suffix.lower()

    if suffix == ".zip":
        extract_dir = Path(extract_dir or tempfile.mkdtemp())
        with zipfile.ZipFile(path) as archive:
            archive.extractall(extract_dir)
        shapefile = _find_single(extract_dir, ".shp")
        return gpd.read_file(shapefile)

    if suffix in (".shp", ".gpkg", ".geojson", ".json"):
        return gpd.read_file(path)

    raise ValueError(
        f"Unsupported catchment file type '{suffix}'. Use a zipped shapefile, "
        "a .gpkg or a .geojson."
    )


def polygon_features(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Keep only valid, non-empty polygon geometries."""
    gdf = gdf.loc[gdf.geometry.notna() & ~gdf.geometry.is_empty].copy()
    is_polygon = gdf.geometry.geom_type.isin(("Polygon", "MultiPolygon"))
    gdf = gdf.loc[is_polygon].copy()
    if gdf.empty:
        raise ValueError("The file contains no polygon geometry.")
    return gdf


def ensure_crs(gdf: gpd.GeoDataFrame, fallback_epsg: int | None = None) -> gpd.GeoDataFrame:
    """Return a GeoDataFrame with a CRS, applying a fallback only if none is set.

    A file with a .prj (shapefile) or embedded CRS (GeoPackage, GeoJSON) needs no
    fallback. When the CRS is genuinely absent, fallback_epsg is assigned; it is
    not a reprojection, it is a statement of what the existing coordinates are.
    """
    if gdf.crs is not None:
        return gdf
    if fallback_epsg is None:
        raise ValueError(
            "The file has no coordinate reference system and cannot be placed on "
            "the SILO grid. Provide the EPSG code its coordinates are in."
        )
    return gdf.set_crs(epsg=int(fallback_epsg))


def attribute_columns(gdf: gpd.GeoDataFrame) -> list[str]:
    """The non-geometry columns, offered to the user for naming a catchment."""
    return [c for c in gdf.columns if c != gdf.geometry.name]


def select_polygon(gdf: gpd.GeoDataFrame, attribute: str | None = None,
                   value: str | None = None):
    """Reduce the features to one catchment and its equal-area polygon.

    With one feature, or attribute/value left as None, every polygon present is
    dissolved together. With an attribute and value, only matching features are
    used. Returns (selected GeoDataFrame, dissolved polygon in AREA_EPSG,
    area_km2).
    """
    selected = gdf
    if attribute is not None and value is not None and str(value) != "":
        as_text = gdf[attribute].astype("string")
        selected = gdf.loc[as_text == str(value)].copy()
        if selected.empty:
            raise ValueError(f"No feature has {attribute} equal to '{value}'.")

    equal_area = selected.to_crs(epsg=AREA_EPSG)
    try:
        polygon = equal_area.geometry.union_all()
    except AttributeError:                      # older GeoPandas
        polygon = equal_area.geometry.unary_union
    if not polygon.is_valid:
        polygon = polygon.buffer(0)
    if polygon.is_empty:
        raise ValueError("The selected catchment polygon is empty.")

    area_km2 = polygon.area / 1_000_000.0
    return selected, polygon, area_km2
