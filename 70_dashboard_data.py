"""70: Build dashboard data and inject into the HTML template.

Usage: python 70_dashboard_data.py <template.html> <output.html>
WHTC multi-project batch rows are kept in the ledger but excluded from
summary-tile sums (they aggregate several developments and can double-count).
"""
import json
import re
import sys

from common import CFG, ROOT

WHTC = re.compile(r"workforce housing tax credit", re.I)


def shorten(p):
    n = p.get("project_name") or p.get("developer_owner") or "?"
    return re.sub(r"\s*\(.*?\)", "", n)[:34]


def oth_summary(incs):
    parts = []
    for i in (incs or [])[:3]:
        amt = i.get("amount_usd")
        parts.append((i.get("type") or "other") + (f" ${amt:,.0f}" if amt else ""))
    if incs and len(incs) > 3:
        parts.append(f"+{len(incs) - 3} more")
    return "; ".join(parts) or None


def build_rows():
    projects = [p for p in json.loads(
        (ROOT / CFG["paths"]["interim"] / "projects.json").read_text(encoding="utf-8"))
        if p["incentive_related"]]
    rows = []
    for i, p in enumerate(projects):
        tif, cost = p.get("tif_amount_usd"), p.get("total_project_cost_usd")
        fh = p.get("fiscal_horizons") or {}
        bh = max((int(k) for k in fh), default=None)
        tbl = fh.get(str(bh)) if bh else None
        rows.append({
            "i": i, "d": p["final_approval_date"],
            "dev": p.get("developer_owner"), "name": p.get("project_name"),
            "short": shorten(p), "type": p["project_type"],
            "addr": p.get("address"), "ura": p.get("urban_renewal_area"),
            "tif": tif, "tifs": p.get("tif_structure"), "cost": cost,
            "tifBasis": p.get("tif_basis"), "tifCash": p.get("tif_amount_cash_basis"),
            "pct": round(100 * tif / cost, 1) if tif and cost else None,
            "oth": oth_summary(p.get("other_incentives")),
            "vote": p.get("vote"), "conf": p.get("confidence") or "low",
            "flags": p.get("flags") or [], "n": p["n_actions"],
            "url": p.get("source_url"),
            "batch": bool(WHTC.search(p.get("project_name") or "")),
            "status": p.get("status") or "approved",
            "compDate": p.get("completion_date"),
            "actualRebate": p.get("actual_rebate_paid"),
            "actualRecip": p.get("actual_rebate_recipient"),
            "actualFy": p.get("actual_rebate_fy"),
            "realized": p.get("assessor_realized_total"),
            "realizedYear": p.get("assessor_year_built"),
            "tifDistrict": p.get("assessor_tif_district"),
            "fhYears": bh,
            "incPaid": tbl["incentive_paid"] if tbl else None,
            "netGain": tbl["net_public_gain_vs_baseline"] if tbl else None,
            "netPublic": tbl["net_taxes_received"] if tbl else None,
        })
    return rows


def build_stats(rows):
    import pandas as pd
    single = [r for r in rows if not r["batch"]]
    interim = ROOT / CFG["paths"]["interim"]
    meetings = len(pd.read_csv(interim / "meetings.csv"))
    n_records = sum(1 for _ in open(interim / "records.jsonl", encoding="utf-8"))
    ss = json.loads((interim / "screen_stats.json").read_text(encoding="utf-8")) \
        if (interim / "screen_stats.json").exists() else {}
    win = CFG["window"]
    fisc = [r for r in single if r["netGain"] is not None]
    return {
        "meetings": meetings, "items": ss.get("items"), "actions": n_records,
        "projects": len(rows),
        "windowStart": win["start"], "windowEnd": win["end"],
        "withTif": sum(1 for r in single if r["tif"]),
        "withCost": sum(1 for r in single if r["cost"]),
        "tifTotal": sum(r["tif"] or 0 for r in single),
        "costTotal": sum(r["cost"] or 0 for r in single),
        "completed": sum(1 for r in rows if r["status"] == "completed"),
        "assessorMatched": sum(1 for r in rows if r["realized"]),
        "withFiscal": len(fisc),
        "netGainTotal": sum(r["netGain"] for r in fisc),
        "incPaidTotal": sum(r["incPaid"] for r in fisc),
    }


def brand_css():
    """Build a token-override :root block from config brand: (empty if unset)."""
    b = CFG.get("brand")
    if not b:
        return ""
    keymap = {
        "surface": "--surface", "card": "--card", "ink": "--ink", "ink2": "--ink-2",
        "ink3": "--ink-3", "line": "--line", "line_soft": "--line-soft",
        "data": "--data", "data_soft": "--data-soft", "warn": "--warn",
        "warn_ink": "--warn-ink", "warn_bg": "--warn-bg",
        "good_ink": "--good-ink", "good_bg": "--good-bg",
    }
    def block(sel, mode):
        decls = " ".join(f"{keymap[k]}:{v};" for k, v in b[mode].items() if k in keymap)
        return f"{sel} {{ {decls} }}"
    # brand override wins in every theme path: default light, both media queries, both stamps
    return "\n".join([
        block(":root", "light"),
        f"@media (prefers-color-scheme: dark) {{ {block(':root', 'dark')} }}",
        block(':root[data-theme="light"]', "light"),
        block(':root[data-theme="dark"]', "dark"),
    ])


def load_iowa():
    p = ROOT / CFG["paths"]["interim"] / "iowa_tif.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def main():
    tpl_path, out_path = sys.argv[1], sys.argv[2]
    rows = build_rows()
    iowa = load_iowa()
    data = json.dumps({"stats": build_stats(rows), "projects": rows,
                       "iowa": iowa}, ensure_ascii=False)
    tpl = open(tpl_path, encoding="utf-8").read()
    assert "__DATA__" in tpl, "template missing __DATA__ placeholder"
    out = tpl.replace("/* __BRAND_OVERRIDE__ */", brand_css()).replace("__DATA__", data)
    from web_util import wrap_page
    open(out_path, "w", encoding="utf-8").write(wrap_page(out))
    print(f"wrote {out_path} ({len(rows)} projects; brand={'on' if CFG.get('brand') else 'off'})")


if __name__ == "__main__":
    main()
