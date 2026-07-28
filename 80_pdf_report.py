"""80: Comprehensive PDF report -> data/outputs/dsm_developer_agreements_report.pdf

Part 1  summary (coverage, key figures, largest TIF commitments, type mix, method)
Part 2  full project ledger (landscape table, all 64 projects)
Part 3  project annex — every field per project incl. timeline and source citation
"""
import importlib
import json
from datetime import date

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (LongTable, PageBreak, Paragraph, SimpleDocTemplate,
                                Spacer, Table, TableStyle)

from common import CFG, ROOT

dash = importlib.import_module("70_dashboard_data")

OUT = ROOT / CFG["paths"]["outputs"] / "dsm_developer_agreements_report.pdf"

_BL = (CFG.get("brand") or {}).get("light", {})
INK = colors.HexColor(_BL.get("ink", "#1a1a19"))
INK2 = colors.HexColor(_BL.get("ink2", "#52514e"))
LINE = colors.HexColor("#c9c8c2")
BLUE = colors.HexColor(_BL.get("data", "#2a78d6"))   # brand accent for headers/rules
PALE = colors.HexColor(_BL.get("data_soft", "#eef3fa"))

ss = getSampleStyleSheet()
S_TITLE = ParagraphStyle("t", parent=ss["Title"], fontName="Times-Bold", fontSize=24,
                         leading=28, textColor=INK, alignment=0, spaceAfter=4)
S_EYE = ParagraphStyle("e", fontName="Helvetica", fontSize=8.5, leading=11,
                       textColor=INK2, spaceAfter=10)
S_H2 = ParagraphStyle("h2", fontName="Helvetica-Bold", fontSize=12, leading=15,
                      textColor=INK, spaceBefore=14, spaceAfter=6)
S_H3 = ParagraphStyle("h3", fontName="Helvetica-Bold", fontSize=9.5, leading=12,
                      textColor=INK, spaceBefore=10, spaceAfter=2)
S_BODY = ParagraphStyle("b", fontName="Helvetica", fontSize=9, leading=12.5,
                        textColor=INK, spaceAfter=5)
S_CELL = ParagraphStyle("c", fontName="Helvetica", fontSize=6.8, leading=8.4, textColor=INK)
S_CELL_R = ParagraphStyle("cr", parent=S_CELL, alignment=2)
S_CELL_B = ParagraphStyle("cb", parent=S_CELL, fontName="Helvetica-Bold")
S_HEAD = ParagraphStyle("ch", fontName="Helvetica-Bold", fontSize=6.8, leading=8.4,
                        textColor=INK)  # dark text on HEAT header for legibility at small size
S_ANX = ParagraphStyle("ax", fontName="Helvetica", fontSize=8, leading=10.8,
                       textColor=INK, spaceAfter=1, leftIndent=10)
S_ANX_H = ParagraphStyle("axh", fontName="Helvetica-Bold", fontSize=9, leading=12,
                         textColor=INK, spaceBefore=9, spaceAfter=2)
S_SRC = ParagraphStyle("src", parent=S_ANX, textColor=INK2, fontSize=7.3)

money = lambda v: f"${v:,.0f}" if v is not None else "—"
esc = lambda s: (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def summary_part(rows, stats):
    win = CFG["window"]
    span = f"{win['start']} – {win['end']}"
    story = [
        Paragraph("Des Moines developer agreements &amp; TIF incentives", S_TITLE),
        Paragraph(f"City Council record · {span} · compiled {date.today().isoformat()} "
                  f"from councildocs.dsm.city (agendas, minutes, council communications)", S_EYE),
        Paragraph("Coverage", S_H2),
        Paragraph(
            f"{stats['meetings']} regular council meetings scanned ({stats['items']:,} agenda items). "
            f"{stats['actions']} incentive-related council actions were fully extracted and collapsed into "
            f"{stats['projects']} distinct projects. Of these, {stats['withTif']} single projects state an explicit "
            f"TIF amount (total {money(stats['tifTotal'])}) and {stats['withCost']} state a total development cost "
            f"(total {money(stats['costTotal'])}; excludes multi-project WHTC batch actions). "
            "All other money cells are blank and flagged — the figure exists only in the signed agreement "
            "exhibit and was never estimated.", S_BODY),
        Paragraph("Largest TIF commitments", S_H2),
    ]
    top = sorted((r for r in rows if r["tif"]), key=lambda r: -r["tif"])[:10]
    data = [[Paragraph(h, S_HEAD) for h in
             ("Project", "Developer / owner", "Type", "TIF", "TIF % of cost", "Project cost", "Structure")]]
    for r in top:
        data.append([
            Paragraph(esc(r["short"]), S_CELL_B), Paragraph(esc(r["dev"]), S_CELL),
            Paragraph(r["type"], S_CELL), Paragraph(money(r["tif"]), S_CELL_R),
            Paragraph(f"{r['pct']:.1f}%" if r["pct"] else "—", S_CELL_R),
            Paragraph(money(r["cost"]), S_CELL_R), Paragraph(esc(r["tifs"]), S_CELL)])
    t = Table(data, colWidths=[95, 100, 62, 48, 44, 52, 210], repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), BLUE),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, PALE]),
        ("GRID", (0, 0), (-1, -1), 0.4, LINE),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    story.append(t)

    counts = {}
    for r in rows:
        counts[r["type"]] = counts.get(r["type"], 0) + 1
    mix = " · ".join(f"{k} {v}" for k, v in sorted(counts.items(), key=lambda kv: -kv[1]))
    story += [
        Paragraph("Project types", S_H2),
        Paragraph(esc(mix) + ". Types are classified from council item text (project names first, "
                  "staff-report notes as fallback); “Other” means the source text does not state a use.", S_BODY),
        Paragraph("Method &amp; honesty notes", S_H2),
        Paragraph(
            "Dollar figures come primarily from Council Communications (staff reports); agendas supply item "
            "descriptions and minutes supply disposition, roll-call number and vote. Multi-meeting deals "
            "(preliminary terms → final terms → amendments) are clustered by address and project identity; "
            "the development-agreement approval is the row of record and prior/subsequent actions appear in the "
            "timeline. TIF % of cost is computed only where both figures are stated. Workforce Housing Tax Credit "
            "batch actions are shown but excluded from summary totals (they aggregate several developments and can "
            "double-count single-project rows). Housing-agency meetings and consent packets are not yet included. "
            "Some 2026 items lack posted minutes; their dispositions are blank.", S_BODY),
    ]
    return story


def ledger_part(rows):
    story = [Paragraph("Project ledger — all projects", S_H2),
             Paragraph("Sorted by TIF amount, then date. “—” = not stated in retrieved documents. "
                       "[batch] rows aggregate several developments.", S_EYE)]
    heads = ("Final action", "Developer / owner", "Project", "Type", "Address", "UR area",
             "TIF", "TIF %", "Cost", "Other incentives", "Vote", "Conf.", "Flags")
    widths = [44, 82, 100, 46, 68, 56, 44, 27, 46, 84, 24, 28, 50]
    scale = 720.0 / sum(widths)
    widths = [w * scale for w in widths]
    data = [[Paragraph(h, S_HEAD) for h in heads]]
    for r in sorted(rows, key=lambda r: (-(r["tif"] or 0), r["d"])):
        flags = ", ".join(f.replace("_", " ") for f in r["flags"] if f != "multi_meeting_project")
        data.append([
            Paragraph(r["d"] + (f" ({r['n']} act.)" if r["n"] > 1 else ""), S_CELL),
            Paragraph(esc(r["dev"]) or "—", S_CELL_B),
            Paragraph(esc(r["name"]) + (" <b>[batch]</b>" if r["batch"] else "") or "—", S_CELL),
            Paragraph(r["type"], S_CELL),
            Paragraph(esc(r["addr"]) or "—", S_CELL),
            Paragraph(esc(r["ura"]) or "—", S_CELL),
            Paragraph(money(r["tif"]), S_CELL_R),
            Paragraph(f"{r['pct']:.1f}%" if r["pct"] else "—", S_CELL_R),
            Paragraph(money(r["cost"]), S_CELL_R),
            Paragraph(esc(r["oth"]) or "—", S_CELL),
            Paragraph(r["vote"] or "—", S_CELL),
            Paragraph(r["conf"], S_CELL),
            Paragraph(esc(flags) or "—", S_CELL)])
    t = LongTable(data, colWidths=widths, repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), BLUE),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, PALE]),
        ("GRID", (0, 0), (-1, -1), 0.4, LINE),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 2.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5),
        ("LEFTPADDING", (0, 0), (-1, -1), 3), ("RIGHTPADDING", (0, 0), (-1, -1), 3),
    ]))
    story.append(t)
    return story


def iowa_part():
    ip = ROOT / CFG["paths"]["interim"] / "iowa_tif.json"
    if not ip.exists():
        return []
    iowa = json.loads(ip.read_text(encoding="utf-8"))
    m, annual, recips = iowa["meta"], iowa["annual"], iowa["recipients"]
    story = [
        Paragraph("Actuals — Iowa Dept. of Management urban-renewal filings", S_H2),
        Paragraph(
            f"The authoritative record of TIF the city actually collected and paid, FY{m['fy_range'][0]}–"
            f"{m['fy_range'][1]}. Over the period Des Moines collected {money(m['total_tif_revenue'])} in "
            f"increment and rebated {money(m['total_rebated_to_developers'])} to developers — an independent "
            f"corroboration of the project-level staff projections above. Actuals lag approvals (rebates flow "
            f"years after completion), so 2020s approvals show little actual payout yet. Source: {m['source']}.", S_BODY),
        Paragraph("Actual TIF by fiscal year", S_H3),
    ]
    head = ["FY", "UR areas", "TIF collected", "Rebated to developers", "Non-rebate spend", "Ending balance"]
    data = [[Paragraph(h, S_HEAD) for h in head]]
    for a in annual:
        data.append([Paragraph(str(a["fy"]), S_CELL), Paragraph(str(a["areas"]), S_CELL_R),
                     Paragraph(money(a["tif_revenue"]), S_CELL_R),
                     Paragraph(money(a["rebated_to_developers"]), S_CELL_R),
                     Paragraph(money(a["non_rebate_spend"]), S_CELL_R),
                     Paragraph(money(a["ending_balance"]), S_CELL_R)])
    t = Table(data, colWidths=[36, 52, 90, 108, 92, 92], repeatRows=1)
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), BLUE),
                           ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, PALE]),
                           ("GRID", (0, 0), (-1, -1), 0.4, LINE), ("VALIGN", (0, 0), (-1, -1), "TOP"),
                           ("TOPPADDING", (0, 0), (-1, -1), 2.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5)]))
    story.append(t)
    story.append(Paragraph("Largest actual rebate recipients (all their projects, FY-range)", S_H3))
    head2 = ["Recipient", "Actual rebate paid", "Payments", "FY range", "Projects (sample)"]
    d2 = [[Paragraph(h, S_HEAD) for h in head2]]
    for r in recips[:20]:
        d2.append([Paragraph(esc(r["recipient"]), S_CELL_B), Paragraph(money(r["actual_rebate_paid"]), S_CELL_R),
                   Paragraph(str(r["payments"]), S_CELL_R), Paragraph(f"{r['fy_first']}–{r['fy_last']}", S_CELL),
                   Paragraph(esc("; ".join(r["projects"])[:120]), S_CELL)])
    t2 = Table(d2, colWidths=[150, 84, 50, 56, 330], repeatRows=1)
    t2.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), BLUE),
                            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, PALE]),
                            ("GRID", (0, 0), (-1, -1), 0.4, LINE), ("VALIGN", (0, 0), (-1, -1), "TOP"),
                            ("TOPPADDING", (0, 0), (-1, -1), 2.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5)]))
    story.append(t2)
    return story


def annex_part():
    projects = [p for p in json.loads(
        (ROOT / CFG["paths"]["interim"] / "projects.json").read_text(encoding="utf-8"))
        if p["incentive_related"]]
    story = [Paragraph("Project annex — full detail and citations", S_H2),
             Paragraph("Every project with its complete council timeline and source citation "
                       "(document URL, page, and verbatim anchor phrase).", S_EYE)]
    for p in sorted(projects, key=lambda p: p["final_approval_date"], reverse=True):
        name = p.get("project_name") or p.get("developer_owner") or "(unnamed)"
        story.append(Paragraph(esc(name), S_ANX_H))
        bits = []
        if p.get("developer_owner"): bits.append(f"<b>Developer/owner:</b> {esc(p['developer_owner'])}")
        bits.append(f"<b>Type:</b> {p['project_type']}")
        if p.get("address"): bits.append(f"<b>Address:</b> {esc(p['address'])}")
        if p.get("urban_renewal_area"): bits.append(f"<b>UR area:</b> {esc(p['urban_renewal_area'])}")
        story.append(Paragraph(" · ".join(bits), S_ANX))
        fin = []
        if p.get("tif_amount_usd") is not None:
            fin.append(f"<b>TIF:</b> {money(p['tif_amount_usd'])}"
                       + (f" (from {p['tif_amount_from']})" if p.get("tif_amount_from") != p["final_approval_date"] else ""))
        if p.get("tif_structure"): fin.append(f"<b>Structure:</b> {esc(p['tif_structure'])}")
        if p.get("total_project_cost_usd") is not None:
            fin.append(f"<b>Total cost:</b> {money(p['total_project_cost_usd'])}")
            if p.get("tif_amount_usd"):
                fin.append(f"<b>TIF/cost:</b> {100 * p['tif_amount_usd'] / p['total_project_cost_usd']:.1f}%")
        if fin: story.append(Paragraph(" · ".join(fin), S_ANX))
        fh = p.get("fiscal_horizons") or {}
        if fh:
            yrs = max(int(k) for k in fh)
            t = fh[str(yrs)]
            story.append(Paragraph(
                f"<b>Public return ({yrs}-yr staff est., all taxing bodies):</b> "
                f"incentive paid {money(t['incentive_paid'])} · net taxes to public "
                f"{money(t['net_taxes_received'])} · net gain vs. baseline "
                f"{money(t['net_public_gain_vs_baseline'])}"
                + (f" (CC {p['fiscal_cc']})" if p.get('fiscal_cc') else ""), S_ANX))
        if p.get("actual_rebate_paid"):
            fy = p.get("actual_rebate_fy") or [None, None]
            story.append(Paragraph(
                f"<b>Actual TIF rebate paid (Iowa DOM):</b> {money(p['actual_rebate_paid'])} "
                f"to {esc(p.get('actual_rebate_recipient'))} across all their projects, "
                f"FY{fy[0]}–FY{fy[1]} (developer total, not project-specific)", S_ANX))
        if p.get("assessor_realized_total"):
            yb = f", building built {p['assessor_year_built']}" if p.get("assessor_year_built") else ""
            td = f" · {esc(p['assessor_tif_district'])}" if p.get("assessor_tif_district") else ""
            story.append(Paragraph(
                f"<b>Assessed value (Polk assessor, current roll):</b> "
                f"{money(p['assessor_realized_total'])}{yb}{td}", S_ANX))
        for inc in p.get("other_incentives") or []:
            amt = f" {money(inc['amount_usd'])}" if inc.get("amount_usd") else ""
            det = f" — {esc(inc['detail'])}" if inc.get("detail") else ""
            story.append(Paragraph(f"<b>Incentive:</b> {inc.get('type', 'other')}{amt}{det}", S_ANX))
        units = []
        if p.get("total_units"): units.append(f"{p['total_units']} units")
        if p.get("affordable_units"): units.append(f"{p['affordable_units']} affordable")
        status_txt = p.get("status")
        if status_txt == "completed" and p.get("completion_date"):
            status_txt = f"built (cert. of completion {p['completion_date']})"
        gov = " · ".join(filter(None, [
            f"<b>Status:</b> {status_txt}" if status_txt else None,
            " ".join(units) or None,
            f"<b>Disposition:</b> {p['disposition']}" if p.get("disposition") else None,
            f"<b>Vote:</b> {p['vote']}" if p.get("vote") else None,
            f"<b>Recusals:</b> {esc(p['recusals'])}" if p.get("recusals") else None,
            f"<b>Resolution:</b> {p['final_resolution_no']}" if p.get("final_resolution_no") else None,
            f"<b>Confidence:</b> {p.get('confidence')}",
            f"<b>Flags:</b> {', '.join(f.replace('_', ' ') for f in p['flags'])}" if p.get("flags") else None]))
        if gov: story.append(Paragraph(gov, S_ANX))
        tl = " → ".join(
            f"{t['date']} {t.get('action') or '?'}" + (f" [{t['resolution']}]" if t.get("resolution") else "")
            for t in p["timeline"])
        story.append(Paragraph(f"<b>Timeline:</b> {esc(tl)}", S_ANX))
        src = f"<b>Source:</b> {p.get('source_url') or '—'}"
        if p.get("source_page"): src += f", p.{p['source_page']}"
        if p.get("anchor_quote"): src += f' — “{esc(p["anchor_quote"])}”'
        story.append(Paragraph(src, S_SRC))
    return story


def main():
    rows = dash.build_rows()
    stats = dash.build_stats(rows)
    doc = SimpleDocTemplate(str(OUT), pagesize=landscape(letter),
                            leftMargin=0.5 * inch, rightMargin=0.5 * inch,
                            topMargin=0.5 * inch, bottomMargin=0.55 * inch,
                            title="Des Moines Developer Agreements & TIF, 2023-2026",
                            author="dsm_dev_agreements pipeline")

    def footer(canvas, _doc):
        canvas.saveState()
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(INK2)
        canvas.drawString(0.5 * inch, 0.3 * inch,
                          "Des Moines developer agreements & TIF · Jul 2023 – Jul 2026 · figures verbatim from councildocs.dsm.city")
        canvas.drawRightString(10.5 * inch, 0.3 * inch, f"p. {canvas.getPageNumber()}")
        canvas.restoreState()

    story = summary_part(rows, stats) + [PageBreak()] + iowa_part() \
        + [PageBreak()] + ledger_part(rows) + [PageBreak()] + annex_part()
    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
