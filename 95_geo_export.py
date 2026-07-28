"""95: Export map layers as GIS files.

Two flavours, both written to data/outputs/geo/:
  * Shapefiles (+ .prj) in the SOURCE CRS — NAD83 Iowa South State Plane US-ft
    (ESRI:102676). Native for ArcGIS Pro and aligns exactly with the user's parcel /
    neighborhood layers, no reprojection needed.
  * GeoJSON in WGS84 (EPSG:4326) — the web/interchange standard.

Shapefile DBF field names are capped at 10 chars, so short names are used and a
field dictionary is written alongside (tif_fields.csv).
"""
import csv
import json
import shutil
from pathlib import Path

import shapefile  # pyshp

import nbhd_util as N
from common import CFG, ROOT

INTERIM = ROOT / CFG["paths"]["interim"]
OUTDIR = ROOT / CFG["paths"]["outputs"] / "geo"
SRC_PRJ = Path(CFG["neighborhoods_shp"]).with_suffix(".prj")

# (shapefile field, type, size, source key, description)
PROJ_FIELDS = [
    ("NAME", "C", 120, "name", "Project name"),
    ("DEVELOPER", "C", 150, "dev", "Developer / owner (counterparty)"),
    ("TYPE", "C", 40, "type", "Project type (classified from item text)"),
    ("ADDRESS", "C", 120, "addr", "Project address"),
    ("TIF_NPV", "N", 14, "tif", "TIF incentive, net present value basis (USD)"),
    ("TIF_BASIS", "C", 40, "tifBasis", "How the TIF figure was established"),
    ("COST", "N", 14, "cost", "Total project cost as stated (USD)"),
    ("TIF_PCT", "N", 8, "pct", "TIF as % of project cost", 1),
    ("NET_GAIN", "N", 14, "netGain", "Projected net public gain vs baseline (USD)"),
    ("ASSESSED", "N", 14, "realized", "Current assessed value, Polk assessor (USD)"),
    ("REBATE_PD", "N", 14, "actual", "Actual TIF rebate paid to developer, Iowa DOM (USD)"),
    ("STATUS", "C", 20, "status", "built (cert. of completion) | approved"),
    ("NBHD", "C", 60, "nbhd", "Recognized neighborhood"),
    ("UR_AREA", "C", 60, "district", "Urban renewal area / TIF district"),
    ("ACTION_DT", "C", 12, "date", "Final council action date"),
    ("SOURCE_URL", "C", 200, "url", "Source document (council communication PDF)"),
]
NB_FIELDS = [
    ("NAME", "C", 60, "name", "Neighborhood name (NHNAME)"),
    ("PROJECTS", "N", 6, "n", "TIF projects located in the neighborhood"),
    ("TIF_NPV", "N", 14, "tif", "Total TIF invested, NPV basis (USD)"),
    ("COST", "N", 14, "cost", "Total stated project cost (USD)"),
    ("NET_GAIN", "N", 14, "netGain", "Total projected net public gain (USD)"),
    ("ASSESSED", "N", 14, "realized", "Total current assessed value of TIF parcels (USD)"),
]


def write_prj(stem):
    if SRC_PRJ.exists():
        shutil.copyfile(SRC_PRJ, OUTDIR / f"{stem}.prj")


def main():
    OUTDIR.mkdir(parents=True, exist_ok=True)
    md = json.loads((INTERIM / "map_data.json").read_text(encoding="utf-8"))

    # ---------- shapefile: projects (points, State Plane) ----------
    with shapefile.Writer(str(OUTDIR / "tif_projects"), shapeType=shapefile.POINT) as w:
        for f in PROJ_FIELDS:
            w.field(f[0], f[1], f[2], f[5] if len(f) > 5 else 0)
        for p in md["projects"]:
            w.point(p["x"], p["y"])
            w.record(*[("" if p.get(f[3]) is None else p.get(f[3])) for f in PROJ_FIELDS])
    write_prj("tif_projects")

    # ---------- shapefile: neighborhoods (polygons, State Plane) ----------
    with shapefile.Writer(str(OUTDIR / "tif_neighborhoods"), shapeType=shapefile.POLYGON) as w:
        for f in NB_FIELDS:
            w.field(f[0], f[1], f[2], 0)
        for nb in md["neighborhoods"]:
            # pyshp expects rings as lists of [x, y]; outer ring clockwise
            w.poly([[list(pt) for pt in ring] for ring in nb["rings"]])
            w.record(*[nb.get(f[3]) or 0 if f[1] == "N" else nb.get(f[3]) or "" for f in NB_FIELDS])
    write_prj("tif_neighborhoods")

    # ---------- GeoJSON (WGS84) ----------
    pfeats = [{"type": "Feature",
               "geometry": {"type": "Point", "coordinates": list(N.to_wgs84(p["x"], p["y"]))},
               "properties": {f[0].lower(): p.get(f[3]) for f in PROJ_FIELDS}}
              for p in md["projects"]]
    (OUTDIR / "tif_projects.geojson").write_text(json.dumps(
        {"type": "FeatureCollection", "features": pfeats}), encoding="utf-8")

    nfeats = []
    for nb in md["neighborhoods"]:
        rings = [[list(N.to_wgs84(x, y)) for x, y in ring] for ring in nb["rings"]]
        nfeats.append({"type": "Feature",
                       "geometry": {"type": "Polygon", "coordinates": rings},
                       "properties": {f[0].lower(): nb.get(f[3]) for f in NB_FIELDS}})
    (OUTDIR / "tif_neighborhoods.geojson").write_text(json.dumps(
        {"type": "FeatureCollection", "features": nfeats}), encoding="utf-8")

    # ---------- district rollup (no geometry) + field dictionary ----------
    with open(OUTDIR / "tif_districts.csv", "w", newline="", encoding="utf-8") as f:
        wr = csv.writer(f)
        wr.writerow(["urban_renewal_area", "projects", "tif_npv_usd", "cost_usd",
                     "net_public_gain_usd", "assessed_value_usd"])
        for d in md["districts"]:
            wr.writerow([d["district"], d["n"], d["tif"], d["cost"], d["netGain"], d["realized"]])

    with open(OUTDIR / "tif_fields.csv", "w", newline="", encoding="utf-8") as f:
        wr = csv.writer(f)
        wr.writerow(["layer", "field", "type", "description"])
        for f_ in PROJ_FIELDS:
            wr.writerow(["tif_projects", f_[0], f_[1], f_[4]])
        for f_ in NB_FIELDS:
            wr.writerow(["tif_neighborhoods", f_[0], f_[1], f_[4]])

    print(f"GIS export -> {OUTDIR}")
    print(f"  tif_projects.shp       {len(md['projects'])} points (State Plane + .prj)")
    print(f"  tif_neighborhoods.shp  {len(md['neighborhoods'])} polygons (State Plane + .prj)")
    print(f"  + WGS84 GeoJSON, tif_districts.csv, tif_fields.csv")


if __name__ == "__main__":
    main()
