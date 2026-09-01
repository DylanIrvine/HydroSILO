"""Catchment-averaged SILO climate, with an optional flow join.

A user uploads a catchment boundary, sets a date range and an email, and gets
the SILO catchment-average climate plus a map of the grid cells used. If they
also provide a flow file, a combined climate-and-flow file is produced, with
flow added in mm/d so it can feed a rainfall-runoff model.

This file is the front end only. The work is in the silo_catchment package.
"""

from __future__ import annotations

import datetime as dt
import io
import tempfile
import zipfile
from pathlib import Path

import pandas as pd
import streamlit as st

import silo_catchment as sc
from silo_catchment.flow import DELIMITERS, DATE_FORMATS, DAY_BOUNDARIES
from silo_catchment.units import FLOW_UNITS

st.set_page_config(page_title="Catchment SILO averaging", layout="wide")

SILO_FIRST_DAY = dt.date(1889, 1, 1)


# --------------------------------------------------------------------------- #
# small helpers
# --------------------------------------------------------------------------- #
def csv_bytes(frame: pd.DataFrame) -> bytes:
    return frame.to_csv(index=False, na_rep="").encode("utf-8")


def xlsx_bytes(frame: pd.DataFrame) -> bytes:
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        frame.to_excel(writer, index=False)
    return buffer.getvalue()


def figure_bytes(figure) -> bytes:
    buffer = io.BytesIO()
    figure.savefig(buffer, format="png", dpi=300, bbox_inches="tight")
    return buffer.getvalue()


def save_uploads(files, folder: Path) -> list[Path]:
    paths = []
    for item in files:
        target = folder / item.name
        target.write_bytes(item.getbuffer())
        paths.append(target)
    return paths


def load_catchment_from_uploads(files, extract_dir: Path):
    """Turn the uploaded file(s) into a GeoDataFrame.

    One .zip/.gpkg/.geojson is read directly. Several files are treated as a
    shapefile set: they are saved together and the .shp among them is read.
    """
    saved = save_uploads(files, extract_dir)
    if len(saved) == 1:
        return sc.load_geodataframe(saved[0], extract_dir=extract_dir)
    shp = [p for p in saved if p.suffix.lower() == ".shp"]
    if not shp:
        raise ValueError(
            "Several files were uploaded but none is a .shp. Upload a zipped "
            "shapefile, a .gpkg or a .geojson, or the full .shp/.shx/.dbf/.prj set."
        )
    return sc.load_geodataframe(shp[0], extract_dir=extract_dir)


# --------------------------------------------------------------------------- #
# header
# --------------------------------------------------------------------------- #
head_text, head_logo = st.columns([3, 1], vertical_alignment='center')

with head_text:
    st.title("HydroSILO")
    st.markdown(
        "Upload a catchment boundary and get the SILO Data Drill climate averaged "
        "over it, sampled by area and weighted by the grid cells the catchment "
        "covers. Add a flow file to also get a combined, model-ready file for  "
        "the associated HydroSTITCH tool that runs lumped parameter catchment models."
        "Note: HydroSILO only works for Australian catchments."
    )
with head_logo:
    st.image('HydroSILO_Logo.png', width='stretch')
# --------------------------------------------------------------------------- #
# 1. request details
# --------------------------------------------------------------------------- #
st.header("1. Request details")
col_email, col_start, col_end = st.columns([2, 1, 1])
with col_email:
    email = st.text_input(
        "Your email (required by SILO)",
        help="SILO's API expects an email as the username. It is used only for "
             "the download request in your session and is not stored or logged.",
    )
    st.caption("Not stored, not logged. Used only for the SILO request.")
with col_start:
    start_date = st.date_input("Start date", value=dt.date(1950, 1, 1),
                               min_value=SILO_FIRST_DAY, max_value=dt.date.today())
with col_end:
    end_date = st.date_input("End date", value=dt.date.today(),
                             min_value=SILO_FIRST_DAY, max_value=dt.date.today())

start_str = start_date.strftime("%Y%m%d")
end_str = end_date.strftime("%Y%m%d")

# --------------------------------------------------------------------------- #
# 2. catchment
# --------------------------------------------------------------------------- #
st.header("2. Catchment boundary")
catchment_files = st.file_uploader(
    "Catchment file: a zipped shapefile, a .gpkg or a .geojson "
    "(or the .shp/.shx/.dbf/.prj set together)",
    type=["zip", "gpkg", "geojson", "json", "shp", "shx", "dbf", "prj", "cpg"],
    accept_multiple_files=True,
)

catchment_ready = False
selected_gdf = polygon = area_km2 = None
default_prefix = "catchment"

if catchment_files:
    try:
        work_dir = Path(tempfile.mkdtemp())
        gdf = load_catchment_from_uploads(catchment_files, work_dir)
        gdf = sc.polygon_features(gdf)

        if gdf.crs is None:
            st.warning("This file has no coordinate reference system.")
            epsg = st.number_input(
                "EPSG code of the file's coordinates "
                "(4283 = GDA94, 7844 = GDA2020)",
                value=4283, step=1,
            )
            gdf = sc.ensure_crs(gdf, fallback_epsg=int(epsg))
        else:
            st.caption(f"Detected CRS: {gdf.crs.to_string()}")

        attribute = value = None
        if len(gdf) > 1:
            st.write(f"The file has {len(gdf)} features. Choose one catchment.")
            col_attr, col_val = st.columns(2)
            with col_attr:
                attribute = st.selectbox("Naming attribute (e.g. StnName)",
                                         sc.attribute_columns(gdf))
            with col_val:
                choices = sorted(gdf[attribute].astype("string").dropna().unique())
                value = st.selectbox("Catchment", choices)
            default_prefix = str(value)
        else:
            default_prefix = Path(catchment_files[0].name).stem

        selected_gdf, polygon, area_km2 = sc.select_polygon(gdf, attribute, value)
        st.success(f"Catchment area: {area_km2:,.1f} km2")
        catchment_ready = True
    except Exception as error:
        st.error(f"Could not read the catchment: {error}")

# --------------------------------------------------------------------------- #
# 3. sampling (advanced)
# --------------------------------------------------------------------------- #
with st.expander("Sampling settings (defaults are usually fine)"):
    col1, col2, col3, col4 = st.columns(4)
    area_per_point = col1.number_input("km2 per sample point", value=25.0, step=5.0)
    min_points = col2.number_input("Minimum points", value=10, step=1)
    max_points = col3.number_input("Maximum points", value=80, step=1)
    seed = col4.number_input("Random seed", value=137, step=1)

# --------------------------------------------------------------------------- #
# 4. output naming and detail
# --------------------------------------------------------------------------- #
st.header("3. Output")
col_prefix, col_detail, col_datefmt = st.columns([2, 1, 1])
with col_prefix:
    raw_prefix = st.text_input("Output filename prefix", value=default_prefix)
with col_detail:
    detail = st.radio("Climate columns", ["Full", "Streamlined"], horizontal=True)
with col_datefmt:
    out_date_label = st.selectbox("Output date format",
                                  ["yyyy-mm-dd", "dd/mm/yyyy"])
out_date_format = "%Y-%m-%d" if out_date_label == "yyyy-mm-dd" else "%d/%m/%Y"
streamlined = detail == "Streamlined"

# a filesystem-safe prefix
prefix = "".join(c if c.isalnum() or c in "-_." else "_"
                 for c in (raw_prefix or "catchment")).strip("_") or "catchment"

# --------------------------------------------------------------------------- #
# 5. optional flow
# --------------------------------------------------------------------------- #
st.header("4. Flow data (optional)")
st.caption("Leave this empty to produce climate only.")
flow_file = st.file_uploader("Flow file (CSV or text)", type=["csv", "txt", "dat"],
                             accept_multiple_files=False)

flow_config = None
if flow_file is not None:
    col_skip, col_delim = st.columns(2)
    skiprows = col_skip.number_input("Rows to skip before the header", value=0, step=1)
    delim_label = col_delim.selectbox("Column delimiter", list(DELIMITERS))
    try:
        raw_flow = sc.load_flow_table(io.BytesIO(flow_file.getvalue()),
                                      skiprows=int(skiprows),
                                      delimiter=DELIMITERS[delim_label])
        st.dataframe(raw_flow.head(8), use_container_width=True)
        columns = list(raw_flow.columns)

        col_d, col_f, col_fmt = st.columns(3)
        date_column = col_d.selectbox("Date (or date-time) column", columns)
        flow_column = col_f.selectbox("Flow column",
                                      columns, index=min(1, len(columns) - 1))
        date_format = col_fmt.selectbox("Date order", list(DATE_FORMATS))

        col_u, col_sub, col_bound = st.columns(3)
        flow_unit = col_u.selectbox("Flow units", FLOW_UNITS)
        subdaily = col_sub.checkbox("Data are sub-daily (average to daily)")
        boundary_label = col_bound.selectbox("Day boundary", list(DAY_BOUNDARIES),
                                             disabled=not subdaily)
        boundary_hour = DAY_BOUNDARIES[boundary_label] if subdaily else 0

        flow_config = dict(raw=raw_flow, date_column=date_column,
                           flow_column=flow_column, date_format=date_format,
                           flow_unit=flow_unit, boundary_hour=boundary_hour)
    except Exception as error:
        st.error(f"Could not read the flow file: {error}")

# --------------------------------------------------------------------------- #
# 6. run
# --------------------------------------------------------------------------- #
st.header("5. Run")
can_run = catchment_ready and bool(email) and ("@" in (email or ""))
if not email:
    st.info("Enter your email to enable the run.")
elif "@" not in email:
    st.warning("That email does not look valid.")
if start_date > end_date:
    st.error("The start date is after the end date.")
    can_run = False

if st.button("Run catchment average", type="primary", disabled=not can_run):
    try:
        nominal = sc.choose_number_of_points(area_km2, float(area_per_point),
                                             int(min_points), int(max_points))
        points = sc.generate_weighted_points(polygon, nominal, seed=int(seed))
        st.write(f"Sampling {nominal} points, {len(points)} unique SILO cells.")

        figure = sc.sampling_map(selected_gdf, points)
        st.pyplot(figure)

        progress_bar = st.progress(0.0)
        status = st.empty()

        def report(done, total, lat, lon):
            progress_bar.progress(done / total)
            status.write(f"Downloading cell {done}/{total}  (lat {lat:.2f}, lon {lon:.2f})")

        climate = sc.download_weighted_average(points, start_str, end_str, email,
                                               progress=report)
        status.write("Download complete.")
        progress_bar.progress(1.0)

        if not streamlined:
            climate = sc.add_derived_columns(climate)
        climate_out = climate.copy()
        if streamlined:
            keep = [c for c in sc.STREAMLINED_COLUMNS if c in climate_out.columns]
            climate_out = climate_out.loc[:, keep]
        climate_out["Date"] = pd.to_datetime(climate_out["Date"]).dt.strftime(out_date_format)

        # assemble the output files as bytes
        outputs: dict[str, bytes] = {}
        outputs[f"{prefix}_SILO_climate_{start_str}_{end_str}.csv"] = csv_bytes(climate_out)
        outputs[f"{prefix}_SILO_points.csv"] = csv_bytes(points)
        outputs[f"{prefix}_SILO_points.png"] = figure_bytes(figure)
        outputs[f"{prefix}_area_km2.txt"] = f"Area_km2: {area_km2:.6f}\n".encode("utf-8")

        summary = "\n".join([
            f"Catchment prefix: {prefix}",
            f"Catchment area_km2: {area_km2:.6f}",
            f"Start date: {start_str}",
            f"End date: {end_str}",
            f"Random seed: {int(seed)}",
            f"km2 per sample point: {float(area_per_point)}",
            f"Nominal sample count: {nominal}",
            f"Unique SILO grid cells: {len(points)}",
            f"Climate detail: {'streamlined' if streamlined else 'full'}",
        ]) + "\n"
        outputs[f"{prefix}_SILO_run_summary.txt"] = summary.encode("utf-8")

        combined_out = None
        if flow_config is not None:
            parsed = sc.parse_flow(flow_config["raw"], flow_config["date_column"],
                                   flow_config["flow_column"], flow_config["date_format"])
            daily_flow = sc.to_daily_mean(parsed, flow_config["boundary_hour"])
            combined = sc.combine_climate_and_flow(
                climate, daily_flow, area_km2, flow_config["flow_unit"],
                streamlined=streamlined, date_format=out_date_format)
            combined_out = combined
            outputs[f"{prefix}_combined_climate_flow.csv"] = csv_bytes(combined)

        # one zip with everything
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as archive:
            for name, data in outputs.items():
                archive.writestr(name, data)

        st.session_state["outputs"] = outputs
        st.session_state["zip_bytes"] = zip_buffer.getvalue()
        st.session_state["zip_name"] = f"{prefix}_SILO_outputs.zip"
        st.session_state["climate_preview"] = climate_out.head(20)
        st.session_state["combined_preview"] = (
            combined_out.head(20) if combined_out is not None else None)
        st.success("Done. Downloads are below.")
    except Exception as error:
        st.error(f"Run failed: {error}")

# --------------------------------------------------------------------------- #
# 7. downloads (persist across reruns via session_state)
# --------------------------------------------------------------------------- #
if "outputs" in st.session_state:
    st.header("6. Downloads")
    st.download_button("Download everything (.zip)",
                       data=st.session_state["zip_bytes"],
                       file_name=st.session_state["zip_name"],
                       mime="application/zip", type="primary")

    st.subheader("Individual files")
    for name, data in st.session_state["outputs"].items():
        mime = ("image/png" if name.endswith(".png")
                else "text/csv" if name.endswith(".csv") else "text/plain")
        st.download_button(name, data=data, file_name=name, mime=mime, key=name)

    if st.session_state.get("climate_preview") is not None:
        st.subheader("Climate preview")
        st.dataframe(st.session_state["climate_preview"], use_container_width=True)
    if st.session_state.get("combined_preview") is not None:
        st.subheader("Combined climate-flow preview")
        st.dataframe(st.session_state["combined_preview"], use_container_width=True)
