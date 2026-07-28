"""97: Build the whole website bundle -> data/outputs/web/

Produces five self-contained HTML files (no external assets, no CDN, no build step —
each can be dropped straight onto a site or opened from disk):
  index.html          landing page linking the views
  dashboard.html      full project ledger + Iowa actuals
  map.html            interactive neighborhood map
  neighborhoods.html  per-neighborhood breakdown
  methodology.html    sources, judgment calls, validation, limitations

Every number on the methodology page is injected from the pipeline's own outputs, so
it cannot drift out of sync with the data on a rebuild.
"""
import csv
import importlib
import json
import re
import statistics
import sys
from datetime import date

from common import CFG, ROOT
from web_util import wrap_page

WEB = ROOT / CFG["paths"]["outputs"] / "web"
INTERIM = ROOT / CFG["paths"]["interim"]

INDEX = """<title>Des Moines TIF & Developer Agreements — 2016–2026</title>
<style>
  :root{ --surface:#faf8f3; --card:#fff; --ink:#211f1a; --ink-2:#57544c; --ink-3:#8c8880;
    --line:#e7e4db; --heat:#e4531c; --heat-2:#c84918; }
  @media (prefers-color-scheme:dark){ :root{ --surface:#17160f; --card:#201e18; --ink:#f5f2e9;
    --ink-2:#c6c2b4; --ink-3:#8c887c; --line:#332f25; --heat:#ef6a38; --heat-2:#e4531c; } }
  *{box-sizing:border-box} body{margin:0;background:var(--surface);color:var(--ink);
    font:15px/1.6 system-ui,-apple-system,"Segoe UI",sans-serif;padding:56px 22px 70px;-webkit-font-smoothing:antialiased}
  .wrap{max-width:880px;margin:0 auto}
  .eyebrow{font-size:10.5px;letter-spacing:.16em;text-transform:uppercase;color:var(--heat);font-weight:700;margin:0 0 6px}
  h1{font-family:"Iowan Old Style",Palatino,Georgia,serif;font-size:clamp(27px,4.5vw,40px);line-height:1.13;margin:0 0 12px;font-weight:600}
  .lede{color:var(--ink-2);max-width:70ch;margin:0 0 30px}
  .tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(130px,1fr));gap:9px;margin-bottom:34px}
  .tile{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:13px 15px}
  .tile .n{font-family:"Iowan Old Style",Palatino,Georgia,serif;font-size:25px;font-weight:600;font-variant-numeric:tabular-nums;line-height:1.1}
  .tile .l{font-size:11.5px;color:var(--ink-2);margin-top:3px}
  .cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:12px}
  a.card{display:block;background:var(--card);border:1px solid var(--line);border-radius:11px;padding:19px 20px;
    text-decoration:none;color:inherit;transition:border-color .12s,transform .12s}
  a.card:hover{border-color:var(--heat);transform:translateY(-2px)}
  a.card h2{font-family:"Iowan Old Style",Palatino,Georgia,serif;font-size:19px;margin:0 0 5px;font-weight:600}
  a.card p{margin:0;font-size:13px;color:var(--ink-2);line-height:1.5}
  a.card .go{color:var(--heat);font-size:12.5px;font-weight:700;margin-top:9px;display:inline-block}
  .foot{margin-top:34px;font-size:12px;color:var(--ink-2);max-width:80ch;line-height:1.6}
  .foot b{color:var(--ink)}
  @media (max-width:640px){
    body{padding:30px 15px 56px}
    .tiles{grid-template-columns:1fr 1fr;gap:7px}
    .tile{padding:11px 12px} .tile .n{font-size:21px}
    .cards{grid-template-columns:1fr;gap:9px}
    a.card{padding:16px 16px}
  }
</style>
<div class="wrap">
  <p class="eyebrow">City of Des Moines · Tax Increment Financing · 2016–2026</p>
  <h1>Ten years of developer agreements &amp; TIF</h1>
  <p class="lede">Every developer agreement, TIF action and public incentive the Des Moines City Council
  approved over a decade — harvested from council agendas, minutes and staff communications, then
  cross-checked against the state's actual TIF filings and the county assessor's roll.</p>
  <div class="tiles">__TILES__</div>
  <div class="cards">
    <a class="card" href="dashboard.html"><h2>Project ledger</h2>
      <p>All __PROJECTS__ projects with terms, projected public return, the state's actual rebate payouts and
      assessed values. Sortable, every row linked to its source PDF.</p><span class="go">Open the ledger →</span></a>
    <a class="card" href="map.html"><h2>Investment map</h2>
      <p>Where the money went, on real neighborhood boundaries. Toggle layers, shade by investment or
      return, click any project for detail.</p><span class="go">Open the map →</span></a>
    <a class="card" href="neighborhoods.html"><h2>Neighborhood breakdown</h2>
      <p>Investment, cost, public return and build status for each of the __NBHDS__ neighborhoods that
      received TIF-backed development.</p><span class="go">Open the breakdown →</span></a>
    <a class="card" href="methodology.html"><h2>Methodology &amp; limitations</h2>
      <p>Where the data comes from, the judgment calls behind the numbers, how they were validated against
      independent sources — and what this can't tell you.</p><span class="go">Read the methodology →</span></a>
  </div>
  <p class="foot"><b>About the figures.</b> TIF amounts are net-present-value — the city's committed, capped
  obligation, not the larger undiscounted cash-basis sum. Where a document doesn't state a figure it is left
  blank and flagged; nothing is estimated. Sources: councildocs.dsm.city (agendas, minutes, council
  communications), Iowa Department of Management urban-renewal filings, Polk County Assessor.</p>
</div>
"""


def fmt_m(v):
    return f"${v/1e6:.0f}M" if v >= 1e7 else f"${v/1e6:.1f}M"


def _nb_key(s):
    """Distinctive tokens of an urban-renewal-area name, for crosswalk agreement."""
    stop = {"des", "moines", "urban", "renewal", "area", "ur", "commercial", "merged", "the", "of"}
    return set(re.sub(r"[^a-z0-9 ]", " ", (s or "").lower()).split()) - stop


def build_methodology(stats, md):
    """Assemble the live figures the methodology page cites."""
    projects = [p for p in json.loads(
        (INTERIM / "projects.json").read_text(encoding="utf-8")) if p["incentive_related"]]
    screen = json.loads((INTERIM / "screen_stats.json").read_text(encoding="utf-8"))
    iowa = json.loads((INTERIM / "iowa_tif.json").read_text(encoding="utf-8"))["meta"]

    basis = {"corrected": 0, "confirmed": 0, "unverified": 0}
    for p in projects:
        b = p.get("tif_basis") or ""
        if "corrected" in b:
            basis["corrected"] += 1
        elif "confirmed" in b:
            basis["confirmed"] += 1
        elif b:
            basis["unverified"] += 1

    pcts = [100 * p["tif_amount_usd"] / p["total_project_cost_usd"] for p in projects
            if p["tif_amount_usd"] and p["total_project_cost_usd"]]
    both = [p for p in projects if p.get("urban_renewal_area") and p.get("assessor_tif_district")]
    crosswalk = sum(1 for p in both
                    if _nb_key(p["urban_renewal_area"]) & _nb_key(p["assessor_tif_district"]))

    with open(INTERIM / "download_log.csv", encoding="utf-8") as f:
        docs = sum(1 for _ in csv.DictReader(f))

    return {
        "windowStart": CFG["window"]["start"], "windowEnd": CFG["window"]["end"],
        "compiled": date.today().isoformat(),
        "meetings": stats["meetings"], "items": screen.get("items"),
        "actions": stats["actions"], "projects": stats["projects"],
        "docs": docs, "tier1": screen.get("tier1"), "tier2": screen.get("tier2"),
        "assessorMatched": stats["assessorMatched"], "completed": stats["completed"],
        "incPaidTotal": stats["incPaidTotal"],
        "n_nbhds": md["meta"]["n_nbhds"], "nbhds_with_tif": md["meta"]["nbhds_with_tif"],
        "unassigned_nbhd": md["meta"]["mapped"] - sum(1 for p in md["projects"] if p.get("nbhd")),
        "basis_corrected": basis["corrected"], "basis_confirmed": basis["confirmed"],
        "basis_unverified": basis["unverified"],
        "median_pct": round(statistics.median(pcts)) if pcts else None,
        "crosswalk": crosswalk, "crosswalk_total": len(both),
        "missing_tif": sum(1 for p in projects if p["tif_amount_usd"] is None),
        "missing_cost": sum(1 for p in projects if p["total_project_cost_usd"] is None),
        "iowa_collected": iowa["total_tif_revenue"],
        "iowa_rebated": iowa["total_rebated_to_developers"],
        "iowa_fy0": iowa["fy_range"][0], "iowa_fy1": iowa["fy_range"][1],
    }


def main():
    WEB.mkdir(parents=True, exist_ok=True)

    # dashboard (70 takes template + out on argv)
    dash = importlib.import_module("70_dashboard_data")
    sys.argv = ["70", str(ROOT / "templates" / "dashboard.html"), str(WEB / "dashboard.html")]
    dash.main()

    importlib.import_module("91_build_map").main()
    importlib.import_module("96_neighborhood_report").main()

    md = json.loads((INTERIM / "map_data.json").read_text(encoding="utf-8"))
    rows = dash.build_rows()
    stats = dash.build_stats(rows)

    # methodology (all figures injected from the pipeline's own outputs)
    meth_tpl = (ROOT / "templates" / "methodology.html").read_text(encoding="utf-8")
    assert "__DATA__" in meth_tpl, "methodology template missing __DATA__"
    (WEB / "methodology.html").write_text(
        wrap_page(meth_tpl.replace("__DATA__", json.dumps(build_methodology(stats, md)))),
        encoding="utf-8")

    # index
    nb_tif = sum(n["tif"] for n in md["nbhd_ranked"])
    tiles = [
        (str(stats["meetings"]), "council meetings scanned"),
        (str(stats["projects"]), "projects captured"),
        (fmt_m(stats["tifTotal"]), "TIF committed (NPV)"),
        (fmt_m(stats["costTotal"]), "development cost"),
        (str(stats["completed"]), "confirmed built"),
        (str(md["meta"]["nbhds_with_tif"]), "neighborhoods reached"),
    ]
    html = (INDEX
            .replace("__TILES__", "".join(
                f'<div class="tile"><div class="n">{a}</div><div class="l">{b}</div></div>'
                for a, b in tiles))
            .replace("__PROJECTS__", str(stats["projects"]))
            .replace("__NBHDS__", str(md["meta"]["nbhds_with_tif"])))
    (WEB / "index.html").write_text(wrap_page(html), encoding="utf-8")

    print(f"\nweb bundle -> {WEB}")
    for f in sorted(WEB.glob("*.html")):
        print(f"  {f.name:22} {f.stat().st_size/1024:7.0f} KB")


if __name__ == "__main__":
    main()
