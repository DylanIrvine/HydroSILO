# HydroSILO

Catchment-averaged SILO climate for Australian catchments, with an optional flow join.

Live app: https://hydrosilo.streamlit.app/

A Streamlit app that takes an Australian catchment boundary and returns the
[SILO Data Drill](https://www.longpaddock.qld.gov.au/silo/) climate averaged over
it, plus a map of the grid cells used. If a flow file is also provided, it builds
a combined climate-and-flow file with flow added in mm/d, ready for a
rainfall-runoff model. The combined file is the input that HydroSTITCH
(https://gr4j-gapfill-webapp.streamlit.app/) expects.

Current version: 1.0 (set by `APP_VERSION` near the top of `app.py`).

## Using it

1. Enter a date range (no email needed: the app uses its own SILO account).
2. Upload the catchment boundary: a zipped shapefile, a `.gpkg` or a `.geojson`.
3. Optionally change the sampling settings, the output prefix, the column detail
   and the date format.
4. Optionally add a flow file and say which columns and units it uses.
5. Run, then download the zip or the individual files.

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
- **Email.** SILO's API expects an email as the username. The app uses its own
  account (dylan.irvine.apps@gmail.com), so users are not asked for theirs. To
  use another account when running your own copy, set the `SILO_USERNAME`
  environment variable.

## Repository layout

```
HydroSILO/
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
    run_counter.py          shared run total (Upstash Redis over REST)
  tests/                    non-network pytest suite and a headless app check
  logo/                     header logo, browser-tab icon and svg source
  requirements.txt
  .streamlit/config.toml    dark theme
  LICENSE
```

## Run locally

```bash
python -m venv .venv
source .venv/bin/activate         # Windows: .venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
```

## Deploying

The public app runs on Streamlit Community Cloud from the `main` branch with
`app.py` as the entry point. The geospatial wheels (`geopandas`, `pyogrio`,
`shapely`, `pyproj`) install from `requirements.txt`; no `apt` packages are
needed because `pyogrio` bundles GDAL.

After pushing a change, reboot the app from the Streamlit Cloud menu. A pull on
its own can leave old copies of the `silo_catchment` modules in memory.

## Privacy and the run counter

- The catchment file is read on the server and held in memory for the session.
  The copy saved to read it is deleted straight away. A flow file is read into
  memory only. Nothing is written to a database or permanent storage.
- To get the climate, the app sends SILO the grid cell coordinates inside the
  catchment and the date range, under the app's own SILO account. The boundary
  file and flow data are not sent.
- The only thing recorded is a running total of completed runs, kept in an
  Upstash Redis database under the key `silo_run_count`. It has no link to any
  user or file.

The counter is optional. To turn it on, add this to the app's Secrets on
Streamlit Cloud, or to `.streamlit/secrets.toml` locally:

```
[upstash]
url = "https://<name>.upstash.io"
token = "<REST token>"
```

Without it the app runs normally and shows no count. `.streamlit/secrets.toml`
is in `.gitignore`. Never commit the token.

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

## How to cite

Irvine, D.J. (2026). HydroSILO (version 1.0) [Web application]. Charles Darwin
University. https://hydrosilo.streamlit.app/

Please also cite the SILO data:

Jeffrey, S.J., Carter, J.O., Moodie, K.B., and Beswick, A.R. (2001). Using
spatial interpolation to construct a comprehensive archive of Australian climate
data. Environmental Modelling and Software 16(4), 309-330.

## Licence

Copyright (c) 2026 Charles Darwin University. All rights reserved. See `LICENSE`.

## Credits

Dylan Irvine, Charles Darwin University. Climate data are from SILO, hosted by
the Queensland Government.
