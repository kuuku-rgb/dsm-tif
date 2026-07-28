"""90: Build map_data.json for the self-contained TIF investment map.

Coordinates are NAD83 Iowa South State Plane (US ft) — used directly for a flat local
vector map (no external tiles). Produces:
  - projects: TIF projects with a point + all metrics (investment, return, realized value)
  - grid: assessed-value landscape, parcels aggregated into square cells (compact)
  - districts: per urban-renewal-area rollup (project count, TIF, net gain, assessed value)
  - bbox, meta
"""
import json
import re
from collections import defaultdict

import nbhd_util as N
from common import CFG, ROOT

INTERIM = ROOT / CFG["paths"]["interim"]
OUT = INTERIM / "map_data.json"
CELL = 660.0  # ft (~1/8 mile) value-grid cell size
WHTC = re.compile(r"workforce housing tax credit", re.I)


def load_neighborhoods():
    """Read neighborhood polygons -> list of {name, rings(simplified), centroid}."""
    shp = str(N.NBHD_SHP)
    shapes = N.read_polygons(shp)
    names = N.read_dbf_field(shp.replace(".shp", ".dbf"), "NHNAME")
    out = []
    for s in shapes:
        if not s["rings"]:
            continue
        out.append({
            "name": names[s["index"]] or f"NBHD {s['index']}",
            "rings": s["rings"],  # full precision for PIP
            "srings": [[[round(x, 1), round(y, 1)] for x, y in N.simplify(r)] for r in s["rings"]],
            "centroid": [round(c, 1) for c in (N.centroid(s["rings"]) or (0, 0))],
        })
    return out


def main():
    projects = [p for p in json.loads((INTERIM / "projects.json").read_text(encoding="utf-8"))
                if p["incentive_related"]]
    geo = json.loads((INTERIM / "parcels_geo.json").read_text(encoding="utf-8"))

    # ---- value grid: sum assessed value + parcel count per cell ----
    cells = defaultdict(lambda: [0, 0.0])  # (gx,gy) -> [n, total_value]
    for x, y, t in zip(geo["x"], geo["y"], geo["total"]):
        if not t:
            continue
        key = (int(x // CELL), int(y // CELL))
        cells[key][0] += 1
        cells[key][1] += t
    grid = [{"x": round((gx + 0.5) * CELL, 1), "y": round((gy + 0.5) * CELL, 1),
             "n": v[0], "val": round(v[1])} for (gx, gy), v in cells.items()]

    # ---- neighborhoods + point-in-polygon assignment ----
    nbhds = load_neighborhoods()

    def which_nbhd(x, y):
        for nb in nbhds:
            if N.point_in_rings(x, y, nb["rings"]):
                return nb["name"]
        return None

    # ---- projects with coordinates ----
    pts, unmapped = [], 0
    nb_stats = defaultdict(lambda: {"n": 0, "tif": 0, "cost": 0, "netGain": 0, "realized": 0})
    for p in projects:
        if not (p.get("x") and p.get("y")):
            unmapped += 1
            continue
        tif = p.get("tif_amount_usd")
        cost = p.get("total_project_cost_usd")
        nb = which_nbhd(p["x"], p["y"])
        if nb and not WHTC.search(p.get("project_name") or ""):
            s = nb_stats[nb]
            s["n"] += 1; s["tif"] += tif or 0; s["cost"] += cost or 0
            s["realized"] += p.get("assessor_realized_total") or 0
            fh = p.get("fiscal_horizons") or {}
            if fh:
                s["netGain"] += fh[str(max(int(k) for k in fh))]["net_public_gain_vs_baseline"]
        pts.append({
            "nbhd": nb,
            "x": p["x"], "y": p["y"],
            "name": p.get("project_name") or p.get("developer_owner") or "?",
            "dev": p.get("developer_owner"),
            "type": p["project_type"],
            "addr": p.get("address"),
            "tif": tif, "tifBasis": p.get("tif_basis"),
            "cost": cost,
            "pct": round(100 * tif / cost, 1) if tif and cost else None,
            "netGain": (p.get("fiscal_horizons") or {}).get(
                str(max((int(k) for k in (p.get("fiscal_horizons") or {})), default=0)), {}
            ).get("net_public_gain_vs_baseline") if p.get("fiscal_horizons") else None,
            "realized": p.get("assessor_realized_total"),
            "actual": p.get("actual_rebate_paid"),
            "status": p.get("status"),
            "district": p.get("assessor_tif_district") or p.get("urban_renewal_area"),
            "date": p.get("final_approval_date"),
            "url": p.get("source_url"),
            "batch": bool(WHTC.search(p.get("project_name") or "")),
        })

    # ---- district rollup (by assessor TIF district where known) ----
    dd = defaultdict(lambda: {"n": 0, "tif": 0, "netGain": 0, "cost": 0, "realized": 0})
    for p in projects:
        d = p.get("assessor_tif_district")
        if not d or WHTC.search(p.get("project_name") or ""):
            continue
        r = dd[d]
        r["n"] += 1
        r["tif"] += p.get("tif_amount_usd") or 0
        r["cost"] += p.get("total_project_cost_usd") or 0
        r["realized"] += p.get("assessor_realized_total") or 0
        fh = p.get("fiscal_horizons") or {}
        if fh:
            h = fh[str(max(int(k) for k in fh))]
            r["netGain"] += h["net_public_gain_vs_baseline"]
    districts = sorted(({"district": k, **v} for k, v in dd.items()),
                       key=lambda r: -r["tif"])

    # attach stats to neighborhood polygons; drop full-precision rings from output
    nb_out = []
    for nb in nbhds:
        s = nb_stats.get(nb["name"], {"n": 0, "tif": 0, "cost": 0, "netGain": 0, "realized": 0})
        nb_out.append({"name": nb["name"], "rings": nb["srings"],
                       "centroid": nb["centroid"], **s})
    nb_ranked = sorted((nb for nb in nb_out if nb["n"]), key=lambda r: -r["tif"])

    vals = [c["val"] for c in grid]
    OUT.write_text(json.dumps({
        "projects": pts, "grid": grid, "districts": districts,
        "neighborhoods": nb_out, "nbhd_ranked": nb_ranked,
        "bbox": geo["bbox"], "cell": CELL,
        "meta": {"mapped": len(pts), "unmapped": unmapped,
                 "grid_cells": len(grid), "parcels": geo["meta"]["n"],
                 "n_nbhds": len(nb_out), "nbhds_with_tif": len(nb_ranked),
                 "val_max": max(vals) if vals else 0,
                 "nb_tif_max": max((r["tif"] for r in nb_ranked), default=0),
                 "crs": "NAD83 Iowa South State Plane (US ft)"},
    }), encoding="utf-8")
    print(f"map_data: {len(pts)} mapped projects ({unmapped} unmapped), "
          f"{len(grid)} grid cells, {len(districts)} districts -> {OUT}")


if __name__ == "__main__":
    main()
