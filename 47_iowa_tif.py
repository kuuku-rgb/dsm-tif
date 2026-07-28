"""47: Iowa Dept. of Management annual TIF data for Des Moines (authoritative actuals).

Source: Iowa Data Hub (idh-be.iowa.gov), public datasets
  779  Urban Renewal Financial Summary by area & fiscal year  -> tif_revenue, rebates
  1002 Local Government TIF Expenditures by Project & Debt     -> rebate_paid_to, amounts

This is the *actual* side to set against the *approved/projected* project data: dollars
the city really collected as increment and really paid back to developers as rebates.
Coverage is FY2012-2024 (state filings lag ~1-2 years).

Outputs data/interim/iowa_tif.json { annual:[...], recipients:[...], meta:{...} }.
50_reconcile.py name-matches recipients to project clusters.
"""
import json

import pandas as pd

from common import CFG, ROOT

EXT = ROOT / CFG["paths"].get("external", "data/external")
CITY = "DES MOINES"
# rebate_paid_to placeholders that are NOT payments to a private developer
NON_DEVELOPER = {"NO REBATE", "NOT A REBATE", "", "CITY OF DES MOINES",
                 "DOWNTOWN SSMID", "HUD SECTION 108 LOAN"}

DATASETS = {
    "financial_779": "https://idh-be.iowa.gov/api/v1/datasets/779/rows.csv",
    "expenditures_1002": "https://idh-be.iowa.gov/api/v1/datasets/1002/rows.csv",
}


def load(name, path):
    df = pd.read_csv(EXT / path)
    return df[df.levy_authority_name == CITY].copy()


def main():
    fin = load("financial_779", "iowa_tif_financial_779.csv")
    exp = load("expenditures_1002", "iowa_tif_expenditures_1002.csv")

    # annual citywide series (actuals)
    annual = []
    for fy, g in fin.groupby("fiscal_year"):
        annual.append({
            "fy": int(fy),
            "areas": int(g.urban_renewal_area_number.nunique()),
            "tif_revenue": round(g.tif_revenue.sum()),
            "rebated_to_developers": round(g.rebate_expenditures.sum()),
            "non_rebate_spend": round(g.non_rebate_expenditures.sum()),
            "ending_balance": round(g.ending_balance.sum()),
        })
    annual.sort(key=lambda r: r["fy"])

    # actual rebate recipients (private developers only)
    reb = exp[exp.rebate_paid_to.notna()].copy()
    reb["recip"] = reb.rebate_paid_to.str.strip()
    reb = reb[~reb.recip.str.upper().isin(NON_DEVELOPER)]
    recipients = []
    for name, g in reb.groupby("recip"):
        recipients.append({
            "recipient": name,
            "actual_rebate_paid": round(g.expenditure_amount.sum()),
            "payments": int(len(g)),
            "fy_first": int(g.fiscal_year.min()),
            "fy_last": int(g.fiscal_year.max()),
            "projects": sorted({str(x)[:60] for x in g.project_description.dropna().unique()})[:5],
        })
    recipients.sort(key=lambda r: -r["actual_rebate_paid"])

    out = {
        "meta": {
            "source": "Iowa Dept. of Management / Iowa Data Hub datasets 779 & 1002",
            "city": CITY,
            "fy_range": [annual[0]["fy"], annual[-1]["fy"]],
            "total_tif_revenue": round(fin.tif_revenue.sum()),
            "total_rebated_to_developers": round(fin.rebate_expenditures.sum()),
            "total_named_developer_rebates": round(sum(r["actual_rebate_paid"] for r in recipients)),
            "note": "Actuals lag approvals; FY2012-2024. Rebates flow years after a project "
                    "completes, so recent (2020s) approvals show little or no actual rebate yet.",
        },
        "annual": annual,
        "recipients": recipients,
    }
    (ROOT / CFG["paths"]["interim"] / "iowa_tif.json").write_text(
        json.dumps(out, indent=1), encoding="utf-8")
    m = out["meta"]
    print(f"Des Moines actual TIF FY{m['fy_range'][0]}-{m['fy_range'][1]}: "
          f"revenue ${m['total_tif_revenue']:,.0f}, rebated ${m['total_rebated_to_developers']:,.0f}; "
          f"{len(recipients)} named developer recipients")


if __name__ == "__main__":
    main()
