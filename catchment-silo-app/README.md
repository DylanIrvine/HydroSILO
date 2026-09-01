# Catchment-averaged SILO climate

A Streamlit app that takes an Australian catchment boundary and returns the
[SILO Data Drill](https://www.longpaddock.qld.gov.au/silo/) climate averaged over
it, plus a map of the grid cells used. If a flow file is also provided, it builds
a combined climate-and-flow file with flow added in mm/d, ready for a
rainfall-runoff model.

It is the interactive, single-catchment version of a batch script: instead of a
checked CSV of file paths, the user uploads one catchment and configures the run
in the browser.

## What it produces

Always:
- `<prefix>_SILO_climate_<start>_<end>.csv` : the catchment-average daily climate.
- `<prefix>_SILO_points.csv` : the unique SILO grid cells used, with weights.
- `<prefix>_SILO_points.png` : a map of those cells over the catchment.
- `<prefix>_area_km2.txt` : the catchment area, also used for the mm/d conversion.
- `<prefix>_SILO_run_summary.txt` : the settings used.

If a flow file is provided, additionally:
- `<prefix>_combined_climate_flow.csv` : climate joined to daily flow by date,
  with flow in both its original units and mm/d.

Everything is also offered as a single `<prefix>_SILO_outputs.zip`.

## How the averaging works

The catchment is projected to GDA94 / Australian Albers (EPSG:3577), an
equal-area projection in metres. A number of sample points is chosen from the
area (one per 25 km2 by default, held between 10 and 80), the points are placed
uniformly by ground area, each is snapped to the 0.05 degree SILO grid, and
repeated cells are collapsed to weights. Each unique cell is downloaded once and
the catchment climate is their weighted daily mean.

## Choices worth knowing

- **CRS.** Read from the file (a shapefile `.prj`, or the CRS embedded in a
  GeoPackage or GeoJSON). You are only asked for an EPSG code if the file has
  none.
- **Shapefile upload.** A shapefile is several files. Upload them as a single
  `.zip`, or use a `.gpkg` or `.geojson`, or select the `.shp/.shx/.dbf/.prj`
  set together.
- **Catchment selection.** One polygon is used as is. A file with several
  features asks for a naming attribute (for example `StnName`) and a value (for
  example `Daly River - Mount Nancar`).
- **mm/d needs area.** mm/d is a depth, so the flow conversion uses the catchment
  area. m3/s to mm/d is `q * 86.4 / area_km2`; ML/d to mm/d is `q / area_km2`.
- **Sub-daily flow.** Averaged to a daily mean. On a 9am boundary, the 24 hours
  ending at 9am on a date are assigned to that date, matching the day-to-9am
  convention used for SILO and BoM rainfall. Midnight uses the calendar date.
- **Excess water** uses Morton wet-environment areal PET. The aridity index keeps
  FAO56. The streamlined output drops the derived columns.
- **Email.** SILO's API expects an email as the username. It is used only for the
  download request in your session. It is not stored or logged.

## Repository layout

```
catchment-silo-app/
  app.py                    Streamlit UI and orchestration only
  silo_catchment/           the hydrology, as plain testable functions
    catchment.py            load shapefile/zip/gpkg, CRS, polygon, area
    sampling.py             area-based weighted sampling, grid snap
    silo.py                 Data Drill download, parse, weighted average
    derived.py              optional derived climate columns
    flow.py                 flexible flow reader and daily aggregation
    combine.py              join climate and flow by date
    units.py                m3/s, ML/d, mm/d conversions
    plotting.py             sampling-cell map
  tests/                    non-network pytest suite
  requirements.txt
  .streamlit/config.toml
```

## Run locally

```bash
python -m venv .venv
source .venv/bin/activate         # Windows: .venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
```

## Deploy on Streamlit Community Cloud

1. Put this folder in a GitHub repository (see the commands below).
2. At [share.streamlit.io](https://share.streamlit.io), sign in with GitHub and
   choose "New app".
3. Select the repository, branch `main`, and `app.py` as the entry point.
4. Deploy. The geospatial wheels (`geopandas`, `pyogrio`, `shapely`, `pyproj`)
   install from `requirements.txt`; no `apt` packages are needed because
   `pyogrio` bundles GDAL.

```bash
git init
git add .
git commit -m "Catchment SILO averaging app"
git branch -M main
git remote add origin https://github.com/<you>/catchment-silo-app.git
git push -u origin main
```

## Notes and limits

- A long record over a large catchment means many cells, each a full daily
  series, downloaded in sequence. This can take minutes and use noticeable
  memory. On the free tier, keep an eye on very large catchments; the sampling
  cap (80 points by default) bounds it.
- Downloads depend on the SILO service being available. Failures on a cell are
  retried a few times before the run stops with a clear message.
- The combined file is designed to drop straight into a daily rainfall-runoff or
  gap-filling workflow: pick a PET column, use `Flow (mm/d)`, and the area is in
  the accompanying text file.

## Tests

```bash
pip install pytest
pytest tests/
```
