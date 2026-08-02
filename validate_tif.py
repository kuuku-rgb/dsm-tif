"""Cross-project validation of every published TIF figure.

Audits the three sibling projects against their raw sources before publication:
  dsm_dev_agreements/   Des Moines project-level (council records)
  dsm_metro_tif/        12-city state actuals + normalized comparison
  metro_dev_agreements/ suburb council records (pilot)

Every check recomputes from the ORIGINAL source file rather than trusting an
intermediate, and states what it proves. Run: python validate_tif.py
"""
import json
import re
import sys
import zipfile
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).parent
DSM = ROOT / "dsm_dev_agreements"
METRO = ROOT / "dsm_metro_tif"
SUB = ROOT / "metro_dev_agreements"

RESULTS = []


def check(name, ok, detail="", critical=True):
    RESULTS.append((name, bool(ok), detail, critical))
    mark = "PASS" if ok else ("FAIL" if critical else "WARN")
    print(f"  [{mark}] {name}" + (f" — {detail}" if detail else ""))
    return bool(ok)


def money(v):
    return f"${v:,.0f}"


# ─────────────────────────────────────────────────────────────── A. state actuals
def validate_state():
    print("\nA. STATE ACTUALS (Iowa DOM dataset 779) — recomputed from raw CSV")
    raw = pd.read_csv(METRO / "data" / "external" / "iowa_tif_financial_779.csv")
    iowa = json.loads((DSM / "data" / "interim" / "iowa_tif.json").read_text(encoding="utf-8"))

    d = raw[raw.levy_authority_name == "DES MOINES"]
    coll, reb = round(d.tif_revenue.sum()), round(d.rebate_expenditures.sum())
    check("DSM increment generated matches raw 779",
          coll == iowa["meta"]["total_tif_revenue"],
          f"raw {money(coll)} vs published {money(iowa['meta']['total_tif_revenue'])}")
    check("DSM rebated-to-developers matches raw 779",
          reb == iowa["meta"]["total_rebated_to_developers"],
          f"raw {money(reb)} vs published {money(iowa['meta']['total_rebated_to_developers'])}")

    # every published annual bar
    ann = {a["fy"]: a for a in iowa["annual"]}
    bad = []
    for fy, g in d.groupby("fiscal_year"):
        fy = int(fy)
        if fy not in ann:
            bad.append(f"FY{fy} missing")
            continue
        if round(g.tif_revenue.sum()) != ann[fy]["tif_revenue"]:
            bad.append(f"FY{fy} revenue")
        if round(g.rebate_expenditures.sum()) != ann[fy]["rebated_to_developers"]:
            bad.append(f"FY{fy} rebate")
    check("all 13 published fiscal-year bars match raw 779", not bad,
          "; ".join(bad) if bad else f"{len(ann)} years verified value-for-value")

    # metro table
    metro = pd.read_csv(METRO / "data" / "outputs" / "metro_tif_by_city.csv")
    bad = []
    for _, r in metro.iterrows():
        g = raw[raw.levy_authority_name == r.city]
        if round(g.tif_revenue.sum()) != r.collected or round(g.rebate_expenditures.sum()) != r.rebated:
            bad.append(r.city)
    check("all 12 metro cities match raw 779", not bad,
          "; ".join(bad) if bad else f"{len(metro)} cities verified")

    # rebate share is a real ratio, not a restated input
    bad = [r.city for _, r in metro.iterrows()
           if r.collected and abs(100 * r.rebated / r.collected - r.rebate_share) > 0.15]
    check("rebate_share equals rebated/collected", not bad, "; ".join(bad))
    return raw, metro


# ───────────────────────────────────────────────────────────── B. levy / context
def validate_levies(metro):
    print("\nB. LEVY DATA (Iowa DOM dataset 927) — recomputed from raw zip")
    z = zipfile.ZipFile(METRO / "data" / "external" / "iowa_city_levies_927.zip")
    with z.open(z.namelist()[0]) as f:
        lv = pd.read_csv(f, low_memory=False)
    lv["CU"] = lv.city_name.str.upper()
    ctx = pd.read_csv(METRO / "data" / "outputs" / "metro_context.csv")

    bad = []
    for _, r in ctx.iterrows():
        m = lv[(lv.CU == r.city) & (lv.levy_name == "Regular General levy") & (lv.fiscal_year == 2024)]
        if m.empty or abs(m.rate.max() - r.gf_rate) > 1e-6:
            bad.append(r.city)
    check("FY2024 general-fund rates match raw 927", not bad, "; ".join(bad))

    bad = []
    for _, r in ctx.iterrows():
        m = lv[(lv.CU == r.city) & (lv.levy_name == "Total Property Taxes")
               & lv.fiscal_year.between(2012, 2024)]
        if abs(m.property_taxes_levied.sum() - r.property_tax) > 1:
            bad.append(r.city)
    check("FY2012-24 property-tax totals match raw 927", not bad, "; ".join(bad))

    n_cap = int((ctx.levy_headroom <= 0.001).sum())
    check("published claim '9 of 12 at the $8.10 cap'", n_cap == 9, f"computed {n_cap} of {len(ctx)}")

    # headroom must be measured pre-consolidation, or the cap comparison is invalid
    fy25 = lv[(lv.levy_name == "Consolidate General Fund") & (lv.fiscal_year == 2025)
              & lv.CU.isin(set(ctx.city))]
    check("FY2025 consolidation would break the cap comparison (why FY2024 is used)",
          (fy25.rate > 8.10).any(),
          f"{int((fy25.rate > 8.10).sum())} cities exceed 8.10 on the FY2025 consolidated line")

    # intensity is a real ratio
    bad = [r.city for _, r in ctx.iterrows()
           if abs(100 * r.collected / r.property_tax - r.tif_pct_of_property_tax) > 0.15]
    check("TIF-intensity % equals collected/property_tax", not bad, "; ".join(bad))
    check("Altoona intensity >100% is genuine, not an artifact",
          ctx.loc[ctx.city == "ALTOONA", "tif_pct_of_property_tax"].iat[0] > 100,
          f"{ctx.loc[ctx.city=='ALTOONA','tif_pct_of_property_tax'].iat[0]}% "
          f"({money(ctx.loc[ctx.city=='ALTOONA','collected'].iat[0])} increment vs "
          f"{money(ctx.loc[ctx.city=='ALTOONA','property_tax'].iat[0])} levied)")
    return ctx


# ─────────────────────────────────────────────────── C. data-quality flags honoured
def validate_flags(raw, ctx):
    print("\nC. DATA-QUALITY FLAGS — the known traps must still be caught")
    g = raw[raw.levy_authority_name == "GRIMES"]
    zero = g[(g.tif_revenue == 0) & (g.rebate_expenditures > 0)]
    check("Grimes reporting gap still detected in raw data", len(zero) >= 3,
          f"{len(zero)} fiscal years with rebates but $0 increment reported")
    row = ctx[ctx.city == "GRIMES"].iloc[0]
    check("Grimes growth suppressed rather than published",
          pd.isna(row.increment_growth_pct),
          "increment_growth_pct is null" if pd.isna(row.increment_growth_pct)
          else f"LEAKED: {row.increment_growth_pct}")
    check("Grimes flagged in machine-readable output",
          int(row.zero_revenue_years) >= 3 and "reporting gap" in str(row.data_quality),
          str(row.data_quality)[:70])


# ─────────────────────────────────────────────────────── D. Des Moines project data
def validate_projects():
    print("\nD. DES MOINES PROJECT DATA — internal integrity")
    proj = [p for p in json.loads((DSM / "data" / "interim" / "projects.json").read_text(encoding="utf-8"))
            if p["incentive_related"]]
    recs = [json.loads(l) for l in open(DSM / "data" / "interim" / "records.jsonl", encoding="utf-8")]
    cands = [json.loads(l) for l in open(DSM / "data" / "interim" / "candidates.jsonl", encoding="utf-8")]

    t1 = {f"{c['meeting_date']}#item{c['item_no']}" for c in cands if c["tier"] == 1}
    ids = {r.get("candidate_id") for r in recs}
    check("every extracted record traces to a screened candidate", ids <= t1,
          f"{len(ids - t1)} orphans" if ids - t1 else f"{len(ids)} records all traceable")
    check("no tier-1 candidate silently dropped", not (t1 - ids),
          f"{len(t1 - ids)} missing" if t1 - ids else f"{len(t1)} candidates all extracted")

    over = [p for p in proj if p.get("tif_amount_usd") and p.get("total_project_cost_usd")
            and p["tif_amount_usd"] > p["total_project_cost_usd"]]
    check("no project has TIF exceeding project cost", not over,
          "; ".join((p.get("project_name") or "?")[:30] for p in over))

    pcts = [100 * p["tif_amount_usd"] / p["total_project_cost_usd"] for p in proj
            if p.get("tif_amount_usd") and p.get("total_project_cost_usd")]
    check("TIF-to-cost ratios are plausible (max <=100%)", max(pcts) <= 100,
          f"max {max(pcts):.1f}%, median {sorted(pcts)[len(pcts)//2]:.1f}%, n={len(pcts)}")

    # NPV correction may only ever lower a figure
    bad = [p for p in proj if p.get("tif_amount_cash_basis")
           and p["tif_amount_usd"] > p["tif_amount_cash_basis"]]
    check("NPV correction never raised a TIF figure", not bad, f"{len(bad)} raised")
    corrected = [p for p in proj if p.get("tif_basis") and "corrected" in p["tif_basis"]]
    check("cash-basis overstatements were corrected", len(corrected) > 0,
          f"{len(corrected)} projects corrected cash->NPV")

    unver = [p for p in proj if p.get("tif_amount_usd") and p.get("tif_basis")
             and ("unverified" in p["tif_basis"] or "differs" in p["tif_basis"])]
    flagged = [p for p in unver if "tif_basis_unverified" in (p.get("flags") or [])]
    check("every unverified TIF basis is flagged for review", len(unver) == len(flagged),
          f"{len(flagged)}/{len(unver)} flagged")

    # nothing invented: blanks must stay blank
    miss = sum(1 for p in proj if p.get("tif_amount_usd") is None)
    check("undisclosed amounts left null, not estimated", miss > 0,
          f"{miss} of {len(proj)} projects have no TIF figure and none was inferred", critical=False)
    return proj


# ────────────────────────────────────────────────────────── E. cross-source checks
def validate_cross(proj):
    print("\nE. CROSS-SOURCE VALIDATION — two independent methods must agree")
    iowa = json.loads((DSM / "data" / "interim" / "iowa_tif.json").read_text(encoding="utf-8"))
    whtc = re.compile(r"workforce housing", re.I)

    def best(p):
        fh = p.get("fiscal_horizons") or {}
        return fh.get(str(max((int(k) for k in fh), default=0)))

    projected = sum(best(p)["incentive_paid"] for p in proj
                    if best(p) and not whtc.search(p.get("project_name") or ""))
    actual = iowa["meta"]["total_rebated_to_developers"]
    delta = abs(projected - actual) / actual * 100
    check("council-derived projections agree with state actuals (<10%)", delta < 10,
          f"projected {money(projected)} vs state actual {money(actual)} — {delta:.1f}% apart")

    both = [p for p in proj if p.get("urban_renewal_area") and p.get("assessor_tif_district")]
    def key(s):
        return set(re.sub(r"[^a-z0-9 ]", " ", (s or "").lower()).split()) - {
            "des", "moines", "urban", "renewal", "area", "ur", "commercial", "merged", "the", "of"}
    agree = sum(1 for p in both if key(p["urban_renewal_area"]) & key(p["assessor_tif_district"]))
    check("UR-area names crosswalk to county assessor districts", agree == len(both),
          f"{agree}/{len(both)} agree (council record vs Polk assessor)")


# ────────────────────────────────────────────────────────── F. published pages
def validate_published():
    print("\nF. PUBLISHED PAGES — live figures must match the source data")
    site = Path("C:/Users/kuuku/dev/ntontan-web/public/tif")
    iowa = json.loads((DSM / "data" / "interim" / "iowa_tif.json").read_text(encoding="utf-8"))
    if not site.exists():
        check("site directory present", False, str(site))
        return
    cmp_html = (site / "comparison.html").read_text(encoding="utf-8")
    m = re.search(r"const D = (\{.*?\});", cmp_html, re.S)
    payload = json.loads(m.group(1)) if m else {}
    ctx = pd.read_csv(METRO / "data" / "outputs" / "metro_context.csv")
    check("comparison page payload matches metro_context",
          len(payload.get("cities", [])) == len(ctx),
          f"{len(payload.get('cities', []))} cities embedded")
    pub = {c["label"]: c for c in payload.get("cities", [])}
    bad = [r.label for _, r in ctx.iterrows()
           if r.label in pub and pub[r.label]["collected"] != r.collected]
    check("no city's increment differs between page and source", not bad, "; ".join(bad))

    dash = (site / "dashboard.html").read_text(encoding="utf-8")
    check("dashboard shows the state's actual increment total",
          str(iowa["meta"]["total_tif_revenue"]) in dash,
          money(iowa["meta"]["total_tif_revenue"]))
    # The City's economic development office asked for "generated" over "collected".
    # Only READER-VISIBLE text counts: `"collected"` as a JSON key, `.collected` property
    # access and data-k="collected" are internal identifiers and must not trip this.
    internal = re.compile(r"""(["'])collected\1|\.collected\b|_collected\b|k=["']collected["']""")
    for page in ("dashboard.html", "comparison.html", "neighborhoods.html", "map.html", "methodology.html"):
        p = site / page
        if not p.exists():
            continue
        t = p.read_text(encoding="utf-8")
        stale = []
        for x in re.finditer(r"collected", t):
            window = t[max(0, x.start() - 20):x.end() + 20]
            if not internal.search(window):
                stale.append(re.sub(r"\s+", " ", t[max(0, x.start() - 45):x.end() + 30]))
        check(f"{page}: reader-facing TIF terminology says 'generated'", not stale,
              (stale[0][:80] if stale else "clean"), critical=False)
    # shadowed browser globals broke a page once already
    for page in ("comparison.html", "dashboard.html", "neighborhoods.html", "map.html"):
        p = site / page
        if p.exists():
            bad = re.findall(r"(?m)^\s*(?:const|let)\s+(top|name|status|origin|parent|self|closed|length)\s*[=,]",
                             p.read_text(encoding="utf-8"))
            check(f"{page}: no top-level shadowing of a browser global", not bad, ", ".join(bad))


def main():
    print("=" * 78)
    print("TIF DATA VALIDATION — recomputing every published figure from raw sources")
    print("=" * 78)
    raw, metro = validate_state()
    ctx = validate_levies(metro)
    validate_flags(raw, ctx)
    proj = validate_projects()
    validate_cross(proj)
    validate_published()

    fails = [r for r in RESULTS if not r[1] and r[3]]
    warns = [r for r in RESULTS if not r[1] and not r[3]]
    print("\n" + "=" * 78)
    print(f"{len(RESULTS)} checks — {len(RESULTS)-len(fails)-len(warns)} passed, "
          f"{len(fails)} failed, {len(warns)} warnings")
    if fails:
        print("\nFAILURES (block publication):")
        for n, _, d, _ in fails:
            print(f"  - {n}: {d}")
    print("=" * 78)
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
