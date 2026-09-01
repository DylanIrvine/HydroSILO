"""Catchment-averaged SILO climate, with an optional flow join.

The hydrology lives here, in plain functions that take and return DataFrames and
GeoDataFrames, so it can be tested and reused without Streamlit. app.py is only a
front end over these functions.
"""

from .catchment import (AREA_EPSG, OUTPUT_EPSG, load_geodataframe,
                        polygon_features, ensure_crs, attribute_columns,
                        select_polygon)
from .sampling import (choose_number_of_points, snap_to_silo_grid,
                       generate_weighted_points)
from .silo import (parse_silo_alldata, download_silo_point,
                   download_weighted_average)
from .derived import add_derived_columns, STREAMLINED_COLUMNS
from .flow import (DATE_FORMATS, load_flow_table, parse_flow, to_daily_mean)
from .units import to_mmd, FLOW_UNITS
from .combine import combine_climate_and_flow
from .plotting import sampling_map

__all__ = [
    'AREA_EPSG', 'OUTPUT_EPSG', 'load_geodataframe', 'polygon_features',
    'ensure_crs', 'attribute_columns', 'select_polygon',
    'choose_number_of_points', 'snap_to_silo_grid', 'generate_weighted_points',
    'parse_silo_alldata', 'download_silo_point', 'download_weighted_average',
    'add_derived_columns', 'STREAMLINED_COLUMNS',
    'DATE_FORMATS', 'load_flow_table', 'parse_flow', 'to_daily_mean',
    'to_mmd', 'FLOW_UNITS', 'combine_climate_and_flow', 'sampling_map',
]
