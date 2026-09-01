"""Non-network tests for the silo_catchment package.

These cover everything except the SILO download itself: catchment loading and
selection, area, sampling, the SILO response parser, derived columns, the flow
reader and daily aggregation, unit conversion and the combine step.
"""

import io
import zipfile
from pathlib import Path

import geopandas as gpd
import pandas as pd
import pytest
from shapely.geometry import Polygon

import silo_catchment as sc


@pytest.fixture
def catchment_gdf():
    poly_a = Polygon([(130.9, -13.9), (131.2, -13.9), (131.2, -13.6), (130.9, -13.6)])
    poly_b = Polygon([(131.3, -14.1), (131.5, -14.1), (131.5, -13.9), (131.3, -13.9)])
    return gpd.GeoDataFrame(
        {"StnName": ["Daly River - Mount Nancar", "Other Gauge"]},
        geometry=[poly_a, poly_b], crs="EPSG:4283",
    )


def test_load_zip_and_gpkg_match(tmp_path, catchment_gdf):
    gpkg = tmp_path / "c.gpkg"
    catchment_gdf.to_file(gpkg, driver="GPKG")
    shp = tmp_path / "c.shp"
    catchment_gdf.to_file(shp)
    zpath = tmp_path / "c.zip"
    with zipfile.ZipFile(zpath, "w") as archive:
        for ext in (".shp", ".shx", ".dbf", ".prj"):
            p = shp.with_suffix(ext)
            if p.exists():
                archive.write(p, p.name)

    for src in (gpkg, zpath):
        gdf = sc.polygon_features(sc.load_geodataframe(src, extract_dir=tmp_path))
        _, _, area = sc.select_polygon(gdf, "StnName", "Daly River - Mount Nancar")
        assert 1000 < area < 1200


def test_missing_crs_fallback(catchment_gdf):
    no_crs = catchment_gdf.copy()
    no_crs.crs = None
    with pytest.raises(ValueError):
        sc.ensure_crs(no_crs)
    fixed = sc.ensure_crs(no_crs, fallback_epsg=4283)
    assert fixed.crs is not None


def test_sampling_weights_sum_to_one(catchment_gdf):
    _, polygon, area = sc.select_polygon(catchment_gdf, "StnName",
                                         "Daly River - Mount Nancar")
    n = sc.choose_number_of_points(area)
    points = sc.generate_weighted_points(polygon, n, seed=137)
    assert abs(points["weight"].sum() - 1.0) < 1e-9
    assert (points["latitude"].round(2) == points["latitude"]).all()


def test_silo_parser_and_excess_water():
    text = (
        "preamble\n"
        "Date     Day Date2      T.Max T.Min Rain Evap Radn VP RHmaxT RHminT FAO56 Mwet Span\n"
        "----     --- -----      ----- ----- ---- ---- ---- -- ------ ------ ----- ---- ----\n"
        "19500101 1 01-01-1950 34 24 10 6 25 30 80 50 5.0 4.0 6.5\n"
    )
    climate = sc.parse_silo_alldata(text.encode())
    derived = sc.add_derived_columns(climate)
    # excess water is Rain minus Morton wet PET, not FAO56
    assert derived.loc[0, "Excess water (mm)"] == pytest.approx(10.0 - 4.0)


def test_flow_reader_and_daily_mean():
    header = ["# meta", "# meta2", "When,Discharge,Quality"]
    base = pd.Timestamp("2001-03-01 00:00")
    body = [f"{(base + pd.Timedelta(hours=h)).strftime('%d/%m/%Y %H:%M')},"
            f"{1.0 + (h % 24) * 0.1:.2f},good" for h in range(48)]
    raw = sc.load_flow_table(io.StringIO("\n".join(header + body)),
                             skiprows=2, delimiter=",")
    parsed = sc.parse_flow(raw, "When", "Discharge", "dd/mm/yyyy")
    midnight = sc.to_daily_mean(parsed, boundary_hour=0)
    nine = sc.to_daily_mean(parsed, boundary_hour=9)
    assert len(midnight) == 2
    # 48 hourly values on a 9am boundary fall across three labelled days
    assert len(nine) == 3


def test_unit_conversions():
    assert sc.to_mmd(1.0, "m3/s", 1000.0) == pytest.approx(0.0864)
    assert sc.to_mmd(1.0, "ML/d", 1000.0) == pytest.approx(0.001)
    assert sc.to_mmd(2.5, "mm/d", 1000.0) == 2.5


def test_combine_adds_mmd():
    climate = pd.DataFrame({"Date": pd.date_range("2001-02-28", periods=5)})
    for c in ("Rain (mm)", "FAO56 PET (mm)",
              "Morton wet-environment areal PET (mm)",
              "Maximum temperature (degC)", "Minimum temperature (degC)"):
        climate[c] = 1.0
    flow = pd.DataFrame({"Date": pd.date_range("2001-03-01", periods=3), "Value": 2.0})
    combined = sc.combine_climate_and_flow(climate, flow, area_km2=1000.0,
                                           flow_unit="m3/s", streamlined=True)
    assert "Flow (mm/d)" in combined.columns
    assert "Flow (m3/s)" in combined.columns
