"""96: Per-neighborhood breakdown -> standalone HTML + CSVs.

Groups located TIF projects by the recognized neighborhood their parcel falls in
(assigned by point-in-polygon in 90_map_data.py) and rolls up investment, cost,
projected public return, assessed value and build status.

Outputs:
  data/outputs/web/neighborhoods.html        self-contained page (drop on a website)
  data/outputs/neighborhoods_summary.csv     one row per neighborhood
  data/outputs/projects_by_neighborhood.csv  one row per project, with its neighborhood
WHTC batch rows are listed but excluded from sums (they aggregate several developments).
"""
import csv
import json
from collections import defaultdict

from common import CFG, ROOT
from web_util import wrap_page

INTERIM = ROOT / CFG["paths"]["interim"]
OUT = ROOT / CFG["paths"]["outputs"]
WEB = OUT / "web"
TPL = ROOT / "templates" / "neighborhoods.html"


def build():
    md = json.loads((INTERIM / "map_data.json").read_text(encoding="utf-8"))
    by_nb = defaultdict(list)
    for p in md["projects"]:
        if p.get("nbhd"):
            by_nb[p["nbhd"]].append(p)

    nbs = []
    for name, projects in by_nb.items():
        real = [p for p in projects if not p["batch"]]  # batch rows excluded from sums
        projects.sort(key=lambda p: -(p["tif"] or 0))
        nbs.append({
            "name": name,
            "n": len(real),
            "tif": sum(p["tif"] or 0 for p in real),
            "cost": sum(p["cost"] or 0 for p in real),
            "netGain": sum(p["netGain"] or 0 for p in real),
            "realized": sum(p["realized"] or 0 for p in real),
            "built": sum(1 for p in real if p["status"] == "completed"),
            "districts": sorted({p["district"] for p in real if p.get("district")}),
            "projects": projects,
        })
    nbs = [n for n in nbs if n["n"]]
    nbs.sort(key=lambda n: -n["tif"])

    stats = {
        "windowStart": CFG["window"]["start"], "windowEnd": CFG["window"]["end"],
        "n_nbhds": md["meta"]["n_nbhds"], "nbhds_with_tif": len(nbs),
        "mapped": sum(n["n"] for n in nbs),
        "unassigned": md["meta"]["mapped"] - sum(len(v) for v in by_nb.values()),
        "tif_total": sum(n["tif"] for n in nbs),
        "cost_total": sum(n["cost"] for n in nbs),
        "gain_total": sum(n["netGain"] for n in nbs),
        "built_total": sum(n["built"] for n in nbs),
    }
    return {"stats": stats, "neighborhoods": nbs}


def main():
    WEB.mkdir(parents=True, exist_ok=True)
    data = build()

    # HTML
    tpl = TPL.read_text(encoding="utf-8")
    assert "__DATA__" in tpl, "template missing __DATA__"
    (WEB / "neighborhoods.html").write_text(
        wrap_page(tpl.replace("__DATA__", json.dumps(data, ensure_ascii=False))), encoding="utf-8")

    # CSVs
    with open(OUT / "neighborhoods_summary.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["rank", "neighborhood", "projects", "built", "tif_npv_usd", "cost_usd",
                    "tif_pct_of_cost", "net_public_gain_usd", "assessed_value_usd",
                    "urban_renewal_areas"])
        for i, n in enumerate(data["neighborhoods"], 1):
            pct = round(100 * n["tif"] / n["cost"], 1) if n["tif"] and n["cost"] else None
            w.writerow([i, n["name"], n["n"], n["built"], n["tif"], n["cost"], pct,
                        n["netGain"], n["realized"], "; ".join(n["districts"])])

    with open(OUT / "projects_by_neighborhood.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["neighborhood", "project", "developer", "type", "tif_npv_usd", "cost_usd",
                    "tif_pct_of_cost", "net_public_gain_usd", "assessed_value_usd",
                    "actual_rebate_paid_usd", "status", "action_date", "urban_renewal_area",
                    "is_batch_row", "source_url"])
        for n in data["neighborhoods"]:
            for p in n["projects"]:
                w.writerow([n["name"], p["name"], p["dev"], p["type"], p["tif"], p["cost"],
                            p["pct"], p["netGain"], p["realized"], p["actual"], p["status"],
                            p["date"], p["district"], p["batch"], p["url"]])

    s = data["stats"]
    print(f"neighborhoods.html + CSVs -> {WEB} / {OUT}")
    print(f"  {s['nbhds_with_tif']} neighborhoods with TIF, {s['mapped']} projects, "
          f"${s['tif_total']:,.0f} TIF, {s['built_total']} built "
          f"({s['unassigned']} located projects outside any neighborhood)")


if __name__ == "__main__":
    main()
