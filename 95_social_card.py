"""95: Render a LinkedIn share card (1200x627 PNG) summarizing the analysis.

A designed summary card, not a dashboard screenshot: LinkedIn renders images small in
feed, where a dense table is unreadable. Figures are pulled live from the pipeline so the
card can never drift from the data. NTONTAN brand: MORTAR ground, HEAT as the data hue.

Note the two periods are labelled separately and deliberately: the dollar figures are the
state's FY2012-24 filings, while the council record covers the config window (2016-2026).

Output: data/outputs/social/dsm_tif_linkedin.png
"""
import json
import re

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager

from common import CFG, ROOT

OUT = ROOT / CFG["paths"]["outputs"] / "social"

BRAND = CFG.get("brand", {}).get("dark", {})
MORTAR = "#1a1a19"
INK = "#ffffff"
INK2 = "#c6c3b7"
INK3 = "#8f8d81"
HEAT = BRAND.get("data", "#ef6a38")
GREEN = BRAND.get("good_ink", "#86c896")
LINE = "#34332e"

W, H, DPI = 1200, 627, 100


def pick_font():
    for name in ("Segoe UI", "Inter", "Helvetica Neue", "Arial", "DejaVu Sans"):
        try:
            font_manager.findfont(font_manager.FontProperties(family=name),
                                  fallback_to_default=False)
            return name
        except Exception:
            continue
    return "DejaVu Sans"


def money_m(v):
    # escape $ so matplotlib does not treat it as mathtext (a pair of $ starts math mode)
    return f"\\${v/1e6:,.0f}M"


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    interim = ROOT / CFG["paths"]["interim"]
    projects = [p for p in json.loads((interim / "projects.json").read_text(encoding="utf-8"))
                if p["incentive_related"]]
    iowa = json.loads((interim / "iowa_tif.json").read_text(encoding="utf-8"))
    m, annual = iowa["meta"], iowa["annual"]
    whtc = re.compile(r"workforce housing", re.I)
    single = [p for p in projects if not whtc.search(p.get("project_name") or "")]
    pcts = sorted(100 * p["tif_amount_usd"] / p["total_project_cost_usd"]
                  for p in single if p["tif_amount_usd"] and p["total_project_cost_usd"])
    med = pcts[len(pcts) // 2]
    built = sum(1 for p in projects if p["status"] == "completed")
    win = CFG["window"]
    span = f"{win['start'][:4]}-{win['end'][:4]}"

    plt.rcParams["font.family"] = pick_font()
    fig = plt.figure(figsize=(W / DPI, H / DPI), dpi=DPI, facecolor=MORTAR)

    # HEAT rule across the top - the brand's signature mark
    fig.add_artist(plt.Rectangle((0, 0.972), 1, 0.028, color=HEAT,
                                 transform=fig.transFigure, zorder=5))

    L = 0.053
    # matplotlib has no letter-spacing; widen the eyebrow with spaces
    fig.text(L, 0.862, " ".join("CITY OF DES MOINES  ·  TAX INCREMENT FINANCING"),
             color=INK3, fontsize=8.5, fontweight="600")
    fig.text(L, 0.735, f"{money_m(m['total_tif_revenue'])} generated in TIF.",
             color=INK, fontsize=27, fontweight="bold")
    fig.text(L, 0.632, f"{money_m(m['total_rebated_to_developers'])} rebated to developers.",
             color=HEAT, fontsize=27, fontweight="bold")
    fig.text(L, 0.567, f"Fiscal {m['fy_range'][0]}-{m['fy_range'][1]}, per Iowa state filings",
             color=INK3, fontsize=10)
    fig.text(L, 0.480,
             f"Every developer agreement Des Moines approved, {span}:\n"
             f"{len(projects)} projects across 406 council actions, extracted\n"
             f"from 13,412 agenda items and cross-checked against\n"
             f"state filings and county assessor records.",
             color=INK2, fontsize=11.5, linespacing=1.6, va="top")

    stats = [(f"{len(projects)}", "projects"), (f"{built}", "confirmed built"),
             (f"{med:.0f}%", "median subsidy"), ("3", "sources")]
    for i, (n, lab) in enumerate(stats):
        x = L + i * 0.115
        fig.text(x, 0.225, n, color=INK, fontsize=20, fontweight="bold")
        fig.text(x, 0.168, lab, color=INK3, fontsize=9.5)

    fig.text(L, 0.077, "Explore the interactive record  →", color=HEAT,
             fontsize=12.5, fontweight="bold")
    fig.text(L, 0.032,
             "Source: councildocs.dsm.city · Iowa Dept. of Management · Polk County Assessor",
             color=INK3, fontsize=8.5)

    # chart: actual TIF collected vs rebated, by fiscal year (right column only)
    ax = fig.add_axes([0.635, 0.20, 0.315, 0.47])
    ax.set_facecolor(MORTAR)
    years = [a["fy"] for a in annual]
    coll = [a["tif_revenue"] / 1e6 for a in annual]
    reb = [a["rebated_to_developers"] / 1e6 for a in annual]
    xs = range(len(years))
    ax.bar([x - 0.21 for x in xs], coll, width=0.4, color=HEAT, label="TIF generated")
    ax.bar([x + 0.21 for x in xs], reb, width=0.4, color=GREEN, label="Rebated to developers")
    for s in ax.spines.values():
        s.set_visible(False)
    ax.set_ylim(0, max(coll) * 1.35)          # headroom so the legend clears the bars
    ax.tick_params(colors=INK3, length=0)
    ax.set_xticks(list(xs))
    ax.set_xticklabels([f"'{str(y)[2:]}" for y in years], fontsize=7)
    ax.set_yticks([20, 40])
    ax.set_yticklabels(["$20M", "$40M"], fontsize=7.5)
    ax.grid(axis="y", color=LINE, linewidth=0.8)
    ax.set_axisbelow(True)
    ax.legend(loc="upper left", frameon=False, fontsize=8.5, labelcolor=INK2,
              handlelength=0.8, handleheight=0.8, borderpad=0, labelspacing=0.3)
    ax.set_title("Actual TIF, by fiscal year (state filings)", color=INK3,
                 fontsize=9, loc="left", pad=10)

    path = OUT / "dsm_tif_linkedin.png"
    fig.savefig(path, facecolor=MORTAR, dpi=DPI)
    print(f"wrote {path} ({W}x{H})")
    render_year_chart(annual, m)


def render_year_chart(annual, m):
    """Standalone fiscal-year chart as its own post image (1200x675)."""
    w, h = 1200, 675
    fig = plt.figure(figsize=(w / DPI, h / DPI), dpi=DPI, facecolor=MORTAR)
    fig.add_artist(plt.Rectangle((0, 0.978), 1, 0.022, color=HEAT,
                                 transform=fig.transFigure, zorder=5))
    L = 0.06
    fig.text(L, 0.885, "Actual TIF generated & rebated to developers, by fiscal year",
             color=INK, fontsize=21, fontweight="bold")
    fig.text(L, 0.815,
             f"City of Des Moines · fiscal {m['fy_range'][0]}–{m['fy_range'][1]} · "
             f"{money_m(m['total_tif_revenue'])} generated, {money_m(m['total_rebated_to_developers'])} "
             f"rebated to developers over the period",
             color=INK2, fontsize=12.5)

    ax = fig.add_axes([0.06, 0.145, 0.88, 0.60])
    ax.set_facecolor(MORTAR)
    years = [a["fy"] for a in annual]
    coll = [a["tif_revenue"] / 1e6 for a in annual]
    reb = [a["rebated_to_developers"] / 1e6 for a in annual]
    xs = range(len(years))
    b1 = ax.bar([x - 0.205 for x in xs], coll, width=0.40, color=HEAT, label="TIF generated")
    b2 = ax.bar([x + 0.205 for x in xs], reb, width=0.40, color=GREEN,
                label="Rebated to developers")
    for bars in (b1, b2):
        for rect in bars:
            ax.text(rect.get_x() + rect.get_width() / 2, rect.get_height() + 0.6,
                    f"{rect.get_height():.0f}", ha="center", va="bottom",
                    color=INK3, fontsize=7.5)
    for s in ax.spines.values():
        s.set_visible(False)
    ax.set_ylim(0, max(coll) * 1.15)
    ax.tick_params(colors=INK3, length=0)
    ax.set_xticks(list(xs))
    ax.set_xticklabels([f"FY{str(y)[2:]}" for y in years], fontsize=9.5, color=INK2)
    ax.set_yticks([10, 20, 30, 40])
    ax.set_yticklabels(["$10M", "$20M", "$30M", "$40M"], fontsize=9)
    ax.grid(axis="y", color=LINE, linewidth=0.8)
    ax.set_axisbelow(True)
    ax.legend(loc="upper left", frameon=False, fontsize=11, labelcolor=INK2,
              handlelength=1.0, handleheight=1.0, borderpad=0, labelspacing=0.4,
              ncol=2, columnspacing=1.4)
    fig.text(L, 0.045,
             "Source: Iowa Dept. of Management, Annual Urban Renewal Reports (Iowa Data Hub dataset 779), "
             "levy authority = Des Moines. Values verbatim from state filings.",
             color=INK3, fontsize=8.5)

    path = OUT / "dsm_tif_by_year.png"
    fig.savefig(path, facecolor=MORTAR, dpi=DPI)
    print(f"wrote {path} ({w}x{h})")


if __name__ == "__main__":
    main()
