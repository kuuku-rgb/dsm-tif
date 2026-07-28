# Des Moines developer agreements & TIF

A reproducible pipeline that harvests City of Des Moines council records, extracts every
developer/owner agreement, TIF action and related public incentive, and cross-checks the
figures against two independent government sources.

**Published views:** https://www.ntontan.com/tif

This repository is public so the method can be scrutinized. If you find an error in the
data or the logic, please open an issue — corrections are welcome and wanted.

## What it produces

| Output | Path |
|---|---|
| Excel workbook (agreements, action log, flags, Iowa actuals) | `data/outputs/dsm_developer_agreements.xlsx` |
| Full PDF report with per-project citations | `data/outputs/dsm_developer_agreements_report.pdf` |
| Flat CSVs behind each tab | `data/outputs/*.csv` |
| Point shapefile of mappable projects | `data/outputs/gis/` |
| Static website (5 self-contained pages) | `data/outputs/web/` |

## Sources

1. **City council records** — agendas, minutes and Council Communications (staff reports)
   from [councildocs.dsm.city](https://councildocs.dsm.city). These give the terms the
   council approved: developer, project, address, incentive amount, vote, resolution number.
2. **Iowa Department of Management** — Annual Urban Renewal Reports via the Iowa Data Hub
   (datasets 779 and 1002). These give what actually happened: increment generated per
   urban-renewal area per fiscal year, and rebates actually paid, by named recipient.
3. **Polk County Assessor** — parcel roll and geometry, for realized assessed value and
   the TIF-district crosswalk. *User-supplied; set `polk_assessor_dbf` / `polk_assessor_csv`
   in `config.yaml` to your own export.*

## Coverage (current run)

- Window **2016-07-01 → 2026-07-14**: 237 regular council meetings, 13,412 agenda items
  screened, 406 incentive-related council actions extracted, clustered into **202 projects**.
- Iowa actuals span **FY2012–FY2024**: $429.2M increment generated, $211.5M rebated to
  developers. (State filings lag; they do not yet cover 2025–26 approvals.)
- 95 projects matched to assessor values; 102 placed on the map.

## Running it

Python 3.12. `pip install pdfplumber requests pandas openpyxl pyyaml reportlab matplotlib pyshp`

Stages run in numeric order and are cached — downloads never re-fetch:

```
00_enumerate_meetings  10_download  20_extract_text  30_screen  35_fetch_communications
40_bundle_candidates   → LLM extraction (see below) →
45_fiscal_tables  46_tif_npv  47_iowa_tif  48_polk_assessor  49_parcel_geo  55_completions
50_reconcile  60_outputs  70_dashboard_data  80_pdf_report  90_shapefiles  96/97 web build
```

Stage 40 writes candidate excerpts to `data/interim/bundles/`; those are read by an LLM and
turned into structured records per `extraction_instructions.md`. The resulting
`data/interim/records.jsonl` **is committed here**, so the analysis downstream of extraction
can be reproduced and audited without re-running that step.

`run_log.md` documents every substantive decision, bug and fix, in order.

## Methodology decisions that affect the numbers

- **Nothing is estimated.** If a council document doesn't state a figure, the field is
  `null` and flagged. A blank means *undisclosed in the public record*, not zero. Roughly
  half the projects have no stated TIF amount because the number lives only in the signed
  agreement exhibit.
- **TIF amounts are net present value**, the capped figure the city commits to — not the
  larger undiscounted "cash basis" sum. Where a source stated both, the NPV is used;
  `tif_basis` records whether that was confirmed, corrected, or unverifiable.
- **State and county incentives are not in the TIF totals.** High Quality Jobs, Workforce
  Housing Tax Credits and job-tied grants are itemized separately under `other_incentives`.
- **Multi-meeting deals are clustered** into one project with a timeline (intent → final
  terms → amendments); the latest controlling figure wins. Clustering requires a shared
  address *and* a compatible developer, so distinct deals at one building stay separate.
- **"Built" means a certificate of completion appears in the record.** This is a floor:
  completions of pre-2016 agreements aren't counted.

## Known limitations

- Regular council meetings only — Housing Agency meetings and consent packets are not
  yet harvested.
- Only projects whose record gives a parcel-matchable street address can be mapped, so
  neighborhood rollups exclude area-described projects (e.g. "vicinity of 1300 Tuttle
  Street") and intersections.
- The assessor roll is a current snapshot, not historical: it shows the finished building
  for completed projects and the pre-development parcel for recent approvals.
- Project-type classification and the corporate/developer split are keyword judgments,
  not official categories.
- Per-project "actual rebate paid" is a *developer-level* citywide total from state
  filings, not a project-specific figure. Don't sum that column.

## License & attribution

Underlying records are public documents from the City of Des Moines, the Iowa Department
of Management and Polk County. Analysis and code by [NTONTAN](https://www.ntontan.com).
