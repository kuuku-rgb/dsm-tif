"""90: Write a georeferenced point shapefile of the projects for GIS.

Geolocates each incentive project at the centroid of its matched Polk parcel(s)
(AllPolk.shp is a point layer, NAD83 State Plane Iowa South / EPSG 102676, US ft) and
carries the full attribute set (TIF on NPV basis, cost, %, net public gain, actual
rebate, assessed value, status, UR area, vote, source). Projects with no address match
can't be placed and are listed in a skipped-count. Copies the source .prj so the output
is properly projected.

Output: data/outputs/gis/dsm_tif_projects.{shp,shx,dbf,prj}
"""
import importlib
import json
import shutil
from pathlib import Path

import shapefile  # pyshp

from common import CFG, ROOT

polk = importlib.import_module("48_polk_assessor")

DBF_PATH = Path(CFG.get("polk_assessor_dbf"))
SHP_PATH = DBF_PATH.with_suffix(".shp")
PRJ_PATH = DBF_PATH.with_suffix(".prj")
OUTDIR = ROOT / CFG["paths"]["outputs"] / "gis"


def build_coord_lookup():
    """(street_key, house) -> (x, y) for Des Moines parcels from AllPolk.shp points."""
    r = shapefile.Reader(str(SHP_PATH))
    fld = [f[0] for f in r.fields[1:]]
    ai, ji = fld.index("ADDRESS"), fld.index("JURISDICT")
    lut = {}
    for sr in r.iterShapeRecords():
        rec = sr.record
        if str(rec[ji]).upper() != "DES MOINES" or not sr.shape.points:
            continue
        sk, house = polk.parse_parcel_address(str(rec[ai]))
        if sk and house is not None:
            lut.setdefault((sk, house), sr.shape.points[0])
    return lut


def project_point(coords, address):
    """Centroid of the parcels a project address matches, or None."""
    pts = []
    for sk, lo, hi in polk.parse_project_address(address):
        for h in range(lo, hi + 1):
            if (sk, h) in coords:
                pts.append(coords[(sk, h)])
    if not pts:
        return None
    return (sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts))


def s(v, n=254):
    return ("" if v is None else str(v))[:n]


def main():
    OUTDIR.mkdir(parents=True, exist_ok=True)
    projects = [p for p in json.loads(
        (ROOT / CFG["paths"]["interim"] / "projects.json").read_text(encoding="utf-8"))
        if p["incentive_related"]]
    coords = build_coord_lookup()

    w = shapefile.Writer(str(OUTDIR / "dsm_tif_projects"), shapeType=shapefile.POINT)
    # field names capped at 10 chars (dBASE limit)
    w.field("proj_name", "C", 100)
    w.field("developer", "C", 120)
    w.field("ptype", "C", 40)
    w.field("address", "C", 100)
    w.field("ura", "C", 60)
    w.field("tif_npv", "N", 12)
    w.field("tif_basis", "C", 40)
    w.field("tif_cash", "N", 12)
    w.field("tif_pct", "N", 6, 1)
    w.field("cost", "N", 14)
    w.field("net_gain", "N", 14)
    w.field("act_rebate", "N", 12)
    w.field("assessed", "N", 14)
    w.field("yr_built", "N", 6)
    w.field("status", "C", 16)
    w.field("fin_date", "C", 10)
    w.field("fin_res", "C", 24)
    w.field("vote", "C", 12)
    w.field("confidence", "C", 8)
    w.field("n_actions", "N", 4)
    w.field("flags", "C", 120)
    w.field("src_url", "C", 200)

    placed = skipped = 0
    for p in projects:
        pt = project_point(coords, p.get("address"))
        if pt is None:
            skipped += 1
            continue
        tif, cost = p.get("tif_amount_usd"), p.get("total_project_cost_usd")
        w.point(pt[0], pt[1])
        w.record(
            s(p.get("project_name"), 100), s(p.get("developer_owner"), 120),
            s(p.get("project_type"), 40), s(p.get("address"), 100),
            s(p.get("urban_renewal_area"), 60),
            tif, s(p.get("tif_basis"), 40), p.get("tif_amount_cash_basis"),
            round(100 * tif / cost, 1) if tif and cost else None,
            cost, _fh(p, "net_public_gain_vs_baseline"), p.get("actual_rebate_paid"),
            p.get("assessor_realized_total"), p.get("assessor_year_built"),
            s(p.get("status"), 16), s(p.get("final_approval_date"), 10),
            s(p.get("final_resolution_no"), 24), s(p.get("vote"), 12),
            s(p.get("confidence"), 8), p.get("n_actions"),
            s(";".join(p.get("flags") or []), 120), s(p.get("source_url"), 200))
        placed += 1
    w.close()
    if PRJ_PATH.exists():
        shutil.copyfile(PRJ_PATH, OUTDIR / "dsm_tif_projects.prj")
    print(f"wrote {OUTDIR / 'dsm_tif_projects.shp'}: {placed} points placed, "
          f"{skipped} projects without a parcel match (not mapped)")


def _fh(p, key):
    fh = p.get("fiscal_horizons") or {}
    if not fh:
        return None
    return fh[str(max(int(k) for k in fh))][key]


if __name__ == "__main__":
    main()
