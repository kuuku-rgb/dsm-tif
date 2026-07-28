"""60: Write Excel workbook + flat CSVs from reconciled data."""
import json

import pandas as pd

from common import CFG, ROOT, read_jsonl

INTERIM = ROOT / CFG["paths"]["interim"]
OUT = ROOT / CFG["paths"]["outputs"]


def best_horizon(p):
    """Return (years, table) for the longest available fiscal horizon, or None."""
    fh = p.get("fiscal_horizons")
    if not fh:
        return None
    yrs = max(int(k) for k in fh)
    return yrs, fh[str(yrs)]


def _fh(p, key):
    bh = best_horizon(p)
    return bh[1][key] if bh else None


def fmt_incentives(incs):
    parts = []
    for i in incs or []:
        amt = f" ${i['amount_usd']:,.0f}" if i.get("amount_usd") else ""
        det = f" ({i['detail']})" if i.get("detail") else ""
        parts.append(f"{i.get('type', 'other')}{amt}{det}")
    return "; ".join(parts) or None


def fmt_timeline(tl):
    return " | ".join(
        f"{t['date']}: {t.get('action') or '?'}"
        + (f" [{t['resolution']}]" if t.get("resolution") else "")
        + (f" ({t['disposition']})" if t.get("disposition") else "")
        for t in tl)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    all_projects = json.loads((INTERIM / "projects.json").read_text(encoding="utf-8"))
    # administrative/non-incentive clusters stay in Actions_long only
    projects = [p for p in all_projects if p["incentive_related"]]
    n_excluded = len(all_projects) - len(projects)
    actions = pd.read_csv(INTERIM / "actions_long.csv")

    agr = pd.DataFrame([{
        "Developer/Owner": p["developer_owner"],
        "Project Name": p["project_name"],
        "Project Type": p["project_type"],
        "Address": p["address"],
        "TIF Amount (USD, NPV basis)": p["tif_amount_usd"],
        "TIF Basis": p.get("tif_basis"),
        "TIF Cash-Basis Figure (USD)": p.get("tif_amount_cash_basis"),
        "TIF % of Cost": (round(100 * p["tif_amount_usd"] / p["total_project_cost_usd"], 1)
                          if p["tif_amount_usd"] and p["total_project_cost_usd"] else None),
        "TIF Structure": p["tif_structure"],
        "Total Project Cost (USD)": p["total_project_cost_usd"],
        "Other Incentives": fmt_incentives(p["other_incentives"]),
        "Status": p.get("status"),
        "Completion Date": p.get("completion_date"),
        "Fiscal Horizon (yrs)": (best_horizon(p) or [None])[0],
        "Incentive Paid gross (USD)": _fh(p, "incentive_paid"),
        "Net Taxes to Public (USD)": _fh(p, "net_taxes_received"),
        "Net Public Gain vs Baseline (USD)": _fh(p, "net_public_gain_vs_baseline"),
        "Actual Rebate Paid to Developer (USD, Iowa DOM)": p.get("actual_rebate_paid"),
        "Actual Rebate Recipient (Iowa DOM)": p.get("actual_rebate_recipient"),
        "Assessed Value (USD, Polk assessor)": p.get("assessor_realized_total"),
        "Assessor Building Year": p.get("assessor_year_built"),
        "Assessor TIF District": p.get("assessor_tif_district"),
        "Affordable Units": p["affordable_units"],
        "Total Units": p["total_units"],
        "Urban Renewal Area": p["urban_renewal_area"],
        "Final Resolution #": p["final_resolution_no"],
        "Final Action": p["final_action_type"],
        "Final Approval Date": p["final_approval_date"],
        "Disposition": p["disposition"],
        "Vote": p["vote"],
        "Recusals": p["recusals"],
        "Confidence": p["confidence"],
        "Flags": ";".join(p["flags"]),
        "Timeline": fmt_timeline(p["timeline"]),
        "TIF Amount From": p["tif_amount_from"],
        "Cost From": p["total_cost_from"],
        "Source URL": p["source_url"],
        "Source Page": p["source_page"],
        "Anchor Quote": p["anchor_quote"],
    } for p in projects])

    flags = agr[(agr.Confidence == "low") | agr.Flags.str.contains("figure_not_in_source", na=False)]

    # Run log tab
    meetings = pd.read_csv(INTERIM / "meetings.csv")
    dl = pd.read_csv(INTERIM / "download_log.csv")
    cands = read_jsonl(INTERIM / "candidates.jsonl")
    records = read_jsonl(INTERIM / "records.jsonl")
    n_t1 = sum(1 for c in cands if c["tier"] == 1)
    n_t2 = len(cands) - n_t1
    missing_tif = sum(1 for p in projects if p["tif_amount_usd"] is None)
    missing_cost = sum(1 for p in projects if p["total_project_cost_usd"] is None)
    runlog = pd.DataFrame([
        ("window", f"{CFG['window']['start']} .. {CFG['window']['end']}"),
        ("meetings enumerated", len(meetings)),
        ("meetings with agenda", int(meetings.agenda_url.notna().sum())),
        ("meetings with minutes", int(meetings.minutes_url.notna().sum())),
        ("documents fetched ok/cached", int(dl.status.isin(["ok", "cached"]).sum())),
        ("download failures", int((~dl.status.isin(["ok", "cached"])).sum())),
        ("tier-1 candidates (full extraction)", n_t1),
        ("tier-2 candidates (logged only)", n_t2),
        ("tier-1 records extracted", len(records)),
        ("projects (deduped, incentive-related)", len(projects)),
        ("non-incentive admin clusters (Actions_long only)", n_excluded),
        ("projects missing TIF amount", missing_tif),
        ("projects missing total cost", missing_cost),
        ("projects in Flags_review", len(flags)),
    ], columns=["metric", "value"])

    # Iowa DOM actuals tabs (authoritative collected/rebated), if present
    iowa_path = INTERIM / "iowa_tif.json"
    iowa = json.loads(iowa_path.read_text(encoding="utf-8")) if iowa_path.exists() else {}
    iowa_annual = pd.DataFrame(iowa.get("annual", []))
    iowa_recip = pd.DataFrame(iowa.get("recipients", []))

    xlsx = OUT / "dsm_developer_agreements.xlsx"
    with pd.ExcelWriter(xlsx, engine="openpyxl") as xw:
        agr.to_excel(xw, sheet_name="Agreements", index=False)
        actions.to_excel(xw, sheet_name="Actions_long", index=False)
        flags.to_excel(xw, sheet_name="Flags_review", index=False)
        if len(iowa_annual):
            iowa_annual.to_excel(xw, sheet_name="Iowa_TIF_actuals_by_year", index=False)
        if len(iowa_recip):
            iowa_recip.to_excel(xw, sheet_name="Iowa_actual_rebate_recipients", index=False)
        runlog.to_excel(xw, sheet_name="Run_log", index=False)
        for name, ws in xw.sheets.items():
            for col in ws.columns:
                width = max((len(str(c.value)) for c in col[:50] if c.value), default=8)
                ws.column_dimensions[col[0].column_letter].width = min(width + 2, 60)

    agr.to_csv(OUT / "agreements.csv", index=False)
    actions.to_csv(OUT / "actions_long.csv", index=False)
    flags.to_csv(OUT / "flags_review.csv", index=False)
    runlog.to_csv(OUT / "run_log.csv", index=False)
    print(f"wrote {xlsx}")
    print(runlog.to_string(index=False))


if __name__ == "__main__":
    main()
