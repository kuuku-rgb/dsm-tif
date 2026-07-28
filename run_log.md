# Run log — DSM developer agreement / TIF harvest

## Step 0 — source inspection (2026-07-14)

Inspected `ag20250929.pdf` / `as20250929.pdf`, plus `ag20250505.pdf`, `ag20250609.pdf`,
`ag20250804.pdf`, `ag20250818.pdf` and Council Communication `25-186`.

**Where the figures live:**
- **Agenda item text**: developer name, project description, address, urban renewal
  area name — but usually **no dollar figures** (exception: bond issuances state
  "not to exceed $X" inline).
- **Minutes**: same item text prefixed with a roll-call number (`25-1278 17. …`) plus
  mover/seconder and vote ("Motion Carried 7-0"). No figures.
- **Council Communications** (`/communications/{YYYY}/{YY-NNN}.pdf`) carry everything:
  header join keys (`Number / Meeting / Agenda Item / Roll Call`), SYNOPSIS with
  developer + principals + address + units + **total project cost**, FISCAL IMPACT with
  the **incentive amount and structure**, funding source = urban renewal area, and
  PREVIOUS COUNCIL ACTION(S) = ready-made project timeline.

**Design tweaks adopted:**
1. New stage `35_fetch_communications.py` — download CCs referenced by tier-1
   candidates only (cost control per §3.2).
2. Enumerate meetings from `councildocs.dsm.city/agendas/` + `/minutes/` directory
   listings (plain HTML indexes) instead of the dsm.city meetings page.
3. Two-tier screening: tier 1 (development agreements, TIF, developer-specific
   incentives) gets full structured extraction; tier 2 (routine urban renewal /
   batch tax abatement / bond items) is logged in Actions_long only.
4. Schema additions: `council_communication_no`, `roll_call_no`,
   `previous_actions` (from CC), provenance `*_from` tags on carried-forward figures.

## Pipeline stages

| stage | script | output |
|---|---|---|
| 00 | 00_enumerate_meetings.py | data/interim/meetings.csv |
| 10 | 10_download.py | data/raw/*.pdf, download_log.csv |
| 20 | 20_extract_text.py | data/text/*.json (per-page text) |
| 30 | 30_screen.py | data/interim/candidates.jsonl |
| 35 | 35_fetch_communications.py | data/raw/cc/*.pdf, data/text/cc/*.json |
| 40 | 40_bundle_candidates.py + Claude-Code-native extraction | data/interim/bundles/, records.jsonl |
| 50 | 50_reconcile.py | data/interim/projects.json, actions_long.csv |
| 60 | 60_outputs.py | data/outputs/dsm_developer_agreements.xlsx + CSVs |

## Run history

- 2026-07-14: window 2023-07-01..2026-07-14 → 71 regular meetings enumerated
  (71 agendas, 69 minutes). First download attempt hit a transient network error;
  added 3× retry with backoff to `common.fetch`.
- 2026-07-14 full run:
  - 140 agenda/minutes PDFs + 100 Council Communications fetched, 0 failures.
  - 3,851 agenda items screened → 109 tier-1 candidates (100 with CC refs),
    172 tier-2 (logged in Actions_long only).
  - Extraction: 7 parallel Claude subagents, 109/109 records emitted to
    records.jsonl; 3 records hand-patched after fetching CCs missed by the
    original single-number CC regex (multi-CC citations "No. X and Y" and CC
    refs outside the captured agenda block; both fixed in 30_screen.py).
  - Reconcile fixes applied during QC: compass/plural abbreviations
    (Southeast→SE), parenthetical stripping, "606 and 666 Walnut" street-number
    expansion, street-number-conflict veto on fuzzy-name merges (stops distinct
    minimum-assessment properties merging), WHTC annual batch items never
    cluster across meetings, non-incentive records can't headline a cluster.
  - Final: 109 records → 71 clusters → 64 incentive-related projects in
    Agreements (7 admin clusters in Actions_long only). 25 projects with an
    explicit TIF amount, 34 with total project cost; 39 missing TIF figure,
    30 missing cost (flagged, not inferred). 13 rows in Flags_review.
  - Output: data/outputs/dsm_developer_agreements.xlsx (+ agreements.csv,
    actions_long.csv, flags_review.csv, run_log.csv).

- 2026-07-15 window extended to 10 years (2016-07-01..2026-07-14):
  - 237 meetings (230 agendas, 234 minutes); 464 agenda/minutes PDFs fetched, 0
    failures. 2016-era PDFs confirmed text-based (no OCR needed).
  - Two robustness fixes: `20_extract_text.py` now logs a stub instead of
    crashing on a corrupt/non-PDF file; `40_bundle_candidates.py` bundles only
    candidates not already in records.jsonl (incremental extraction).
  - 13,412 agenda items screened → 406 tier-1 candidates (109 already extracted,
    297 new) + 608 tier-2. 297 new extracted by parallel Claude subagents into
    records_v2_b*.jsonl (a mid-run session-limit interruption cost 6 bundles;
    re-run recovered them — 32/38 shards had already landed on disk). Merged to
    406 records with 0 missing / 0 dupes.
  - 406 records → 212 clusters → 191 incentive-related projects (21 admin-only).
    Non-batch totals: TIF $231.7M across 83 projects; cost $3.42B across 113.
    108 projects missing TIF figure, 76 missing cost; 53 in Flags_review.
  - Dashboard/PDF stat counts made dynamic (read meetings.csv, records.jsonl,
    screen_stats.json, config window) — no more hardcoded 3-year numbers.
  - Note: "Financial Center hotel conversion" and "Financial Center office-to-
    housing" are kept as SEPARATE projects — the 606 Walnut deal pivoted from a
    hotel plan to housing; merging would conflate a superseded plan with the
    built project. Verify if a single lineage is preferred.

- 2026-07-15 added net-fiscal-impact + outcome tracking (new stages 45, 55):
  - `45_fiscal_tables.py` parses the staff "estimated taxes with/without project"
    tables from CC PDFs (113 CCs → per-project 10/20/30-yr rows: taxes_without,
    taxes_with, incentive_paid, net_taxes_received, net_public_gain_vs_baseline).
    58 of 191 projects now carry a fiscal table. Aggregate (best horizon each,
    non-batch): $216M gross incentive → $545M net public gain vs. baseline.
  - `55_completions.py` scans agendas/minutes for certificates of completion
    (173) and terminations (2); `50_reconcile.py` matches them to clusters by
    address/developer and sets project `status` (completed/approved/terminated)
    + `completion_date`. 44 projects confirmed built. NOTE: this is a FLOOR —
    completions of pre-2016 agreements and unmatched entity names aren't counted.
  - Surfaced in all outputs: dashboard gains "net public gain" + "confirmed
    built" stat tiles, a Net-public-gain column, and Status chips; Excel gains
    Status/Completion Date/Fiscal Horizon/Incentive Paid/Net Taxes/Net Gain
    columns; PDF annex gains a "Public return" line and Status per project.
  - Pipeline order is now 00 10 20 30 35 40 45 50 55(before 50) 60 70 80; run
    45 and 55 before 50 (50 consumes fiscal_tables.json + completions.jsonl).

- 2026-07-15 added Iowa DOM actuals + fixed a clustering over-merge (stage 47):
  - `47_iowa_tif.py` pulls two Iowa Data Hub datasets (public, no auth):
    779 (financial summary) + 1002 (expenditures by project). Filtered to city
    "DES MOINES", cached in data/external/*.csv. Produces iowa_tif.json: annual
    citywide series (FY2012-2024) + named rebate recipients.
  - Authoritative actuals: $429.2M TIF collected, $211.5M rebated to developers
    FY12-24. CROSS-CHECK: our project-level staff-table projections summed to
    $215.8M — within 2% of the state's $211.5M actual rebates. Strong validation.
  - `50_reconcile.py` name-matches recipients to clusters (actual_rebate_paid) —
    NOTE this is a DEVELOPER-level citywide total (e.g. Merle Hay Mall's total
    spans all phases), not project-specific; never sum the column.
  - Clustering fix: the Iowa join exposed an address-only over-merge (American
    Equity + Maverik/Kum&Go both at 1100 Locust merged into one project).
    `same_project` now requires developer compatibility (or matching project
    name) to merge on a shared address. Mixed-developer clusters 35 -> 32 (the
    remainder are legit project-LLC/parent name variants). Projects 191 -> 195.
  - Surfaced everywhere: dashboard gains an "actuals" band (annual collected-vs-
    rebated chart, top-recipients chart, 2 stat tiles, actual-rebate column);
    Excel gains Iowa_TIF_actuals_by_year + Iowa_actual_rebate_recipients tabs;
    PDF gains an "Actuals — Iowa DOM" section + per-project actual line.
  - Iowa data lags: FY2012-2024 only; 2025-26 approvals have no actuals yet.

- 2026-07-15 added Polk County assessor join (stage 48):
  - Source: user's parcel export at QCT/POLKCOUNTY - POLKCOUNTY.csv (path in
    config `polk_assessor_csv`). A commercial/TIF parcel subset (6,145 DSM
    parcels). `48_polk_assessor.py` builds a street->parcels index; parses messy
    project addresses (ranges "3404-3422", lists "200, 210, and 216") and matches
    by house-number-in-range. (Gotcha: `house` column is float — cast int(float()).)
  - `50_reconcile.py` attaches realized assessed value (land/bldg/total),
    building year, and the assessor's TIF-district name per project. 70/195
    projects matched (commercial-subset limits coverage; residential often absent).
  - VALIDATION: assessor `tif_descr` (e.g. "DES MOINES INGERSOLL-GRAND COMMERCIAL
    UR") crosswalks to our extracted urban_renewal_area — 49/49 projects that have
    both share a distinctive token. Independent confirmation of the UR-area field.
  - Projected-vs-realized (completed projects): District at 6th cost $40.6M ->
    assessed $39.6M; affordable (Union at Rivers Edge $56M -> $17.4M) assess far
    below cost as restricted-rent housing does. 23 completed projects have values.
  - CAVEAT: assessor is a CURRENT-roll snapshot (Nov 2025). Reflects finished
    building for completed projects, pre-development parcel for recent approvals.
  - Surfaced: dashboard "Assessed value" column + coverage note; Excel 3 columns;
    PDF annex "Assessed value" line.
  - 2026-07-15 upgraded to the FULL parcel roll (AllPolk.dbf, 219,806 records /
    88,101 Des Moines) as the primary value source; CSV kept only for tif_descr.
    `48_polk_assessor.py` now streams the dBASE file (no deps) and parses the
    combined ADDRESS string. Config: `polk_assessor_dbf` + `polk_assessor_csv`.
    Two parser fixes were essential: (a) numbered streets ("108 3rd", "1601 6th
    Ave") — the street-part regex required a leading letter, dropping every
    numbered avenue; (b) strip trailing ", Des Moines, IA <zip>" so it doesn't
    leak into the street name. Match rate 70 -> 95/195; UR crosswalk 49/49 ->
    62/62 agree; completed-with-value 23 -> 33. (assessorMatched stat counts
    nonzero values; ~8 projects match only $0 exempt parcels.)

- 2026-07-15 fixed a cluster over-merge + figure scope-mismatch (Southridge):
  - User caught a 480% TIF/cost row. Cause: a 2023 Native Business Services
    "$2M sidewalk" item merged into the Macerich/Genesis Health Club deal because
    both are at Southridge Mall — `dev_compatible` accepted a single shared name
    BIGRAM ("southridge mall", a location) as merge evidence. Then the headline
    (a figureless 2021 amendment) carried TIF $9.6M from the 2020 Genesis record
    but cost $2M from the 2023 sidewalk record -> absurd ratio.
  - Fixes in `50_reconcile.py`: (1) `dev_compatible` no longer merges on a shared
    bigram — requires project-name similarity >=0.7 (or similar developer);
    (2) cost now prefers the SAME record that supplied the TIF (same scope);
    (3) new flag `tif_exceeds_cost_check_scope` if TIF>cost slips through.
  - Result: Genesis now TIF $9.6M / cost $16.5M = 58% (matches its CC's stated
    "~58% of total project costs"); Native sidewalk is its own project; 0
    remaining TIF>cost rows; max TIF% is 58%. Projects 195 -> 202 (tighter
    clustering; legit multi-action projects like 1601 6th Ave (9 actions),
    Foundry Lofts (4) intact).

- 2026-07-15 fixed systematic cash-vs-NPV TIF overstatement (stage 46):
  - User flagged that TIF/cost still felt high. Root cause: staff reports state
    TIF two ways — a larger "cash basis" (nominal sum) and a smaller NPV
    (discounted). The city commits to / reports the NPV and computes its "% of
    project cost" on it; structured extraction had grabbed cash-basis for ~25%
    of projects, overstating TIF 40-75%.
  - `46_tif_npv.py` recovers the canonical NPV per CC: prefers "capped maximum
    amount of assistance at $X ... net present value" (the committed cap, summed
    across phases), then an explicit "total $X NPV", then a labeled NPV amount.
    Guards: (a) a cap+its-own-estimate are NOT summed as two phases (Carpenter
    23-360 double-counted $4.0M cap + $3.88M estimate -> was $7.88M, now $4.0M);
    (b) if a "cash basis" figure is SMALLER than the labeled NPV, the source
    reversed its labels (Exodus 22-350 literally says "$9,016,148 on a NPV
    ($5,724,899 cash)" — impossible) -> take the smaller as NPV.
  - `50_reconcile.py` sets tif_amount_usd to the NPV when the CC provides one and
    it is < the extracted figure (only lowers, never raises); keeps the cash
    figure in tif_amount_cash_basis; labels tif_basis: corrected-from-cash (23),
    confirmed (17), unverified-no-NPV-in-source (37), as-extracted-CC-differs (8).
    Unverified/differs get flag `tif_basis_unverified` (-> Flags_review).
  - Result: TIF% median 14% -> 10%; the inflated 29-35% cases dropped to their
    CC-stated levels (Carpenter 29->18% [CC 17.7%], Merge 23->16% [CC 14%],
    Exodus 35->22%). Max is Genesis 58% — its CC's OWN stated figure (a large
    sports-complex increment deal), confirmed, not an error.
  - Outputs: dashboard TIF cell shows basis + cash figure on hover, "?" chip on
    unverified; Excel adds TIF Basis + Cash-Basis columns; coverage note explains.

- 2026-07-15 added GIS output (stage 90):
  - `90_shapefiles.py` writes data/outputs/gis/dsm_tif_projects.{shp,shx,dbf,prj}
    — a POINT layer, one point per incentive project at the centroid of its
    matched Polk parcel(s). Uses pyshp (installed); reads AllPolk.shp (itself a
    point layer, NAD83 State Plane Iowa South / EPSG 102676, US ft) directly for
    coordinates, so it's independent of the polk_index. Copies AllPolk.prj.
  - 22 attribute fields (dBASE 10-char names): proj_name, developer, ptype,
    address, ura, tif_npv, tif_basis, tif_cash, tif_pct, cost, net_gain,
    act_rebate, assessed, yr_built, status, fin_date, fin_res, vote, confidence,
    n_actions, flags, src_url.
  - 102 of 202 projects placed (71 approved, 31 completed); 100 unplaced (no
    parcel match — not-yet-built, area/lot-described, or unmatched). Reprojection
    to WGS84 GeoJSON deferred (pyproj not installed); shapefile ships in native
    State Plane with its .prj, reprojectable in any GIS.

- 2026-07-15 added spatial map (stages 49, 90 + map artifact):
  - `49_parcel_geo.py` reads AllPolk.shp (Point geom, NAD83 Iowa South State
    Plane ft) aligned record-for-record with the dbf; exports 88,101 DSM parcel
    points + assessed value. `48_polk_assessor.py` now carries x,y per indexed
    parcel; match_address returns a centroid, so `50` stamps each project with a
    map point. 107/202 projects have coordinates.
  - `90_map_data.py` builds map_data.json (0.28MB): project points w/ metrics,
    an assessed-value grid (parcels aggregated into 660ft cells, 3920 cells), and
    per-UR-area rollups. Self-contained Canvas map artifact (no external tiles —
    artifact CSP blocks them; vector value-landscape background instead).
  - Concentration finding: Metro Center Merged UR holds 55 projects, $82.2M TIF,
    $164.7M net public gain, $550M realized assessed value — TIF is heavily
    downtown-clustered.
  - LIMIT: assessor export is a single snapshot (TOTAL_OLD ~= TOTAL_FULL, no real
    YoY change), so true before/after "surrounding building" impact isn't
    derivable from parcels; the map shows the value LANDSCAPE + per-project
    increment (realized value) + district totals. Temporal increment growth is
    the Iowa FY2012-24 series (main dashboard). Projected-assessed-value from CCs
    was too inconsistently phrased (~8 CCs) to use as a field — skipped.
  - Map artifact is SEPARATE from the dashboard (own URL). Could not visually
    verify render (browser pane gated); validated data + structure mechanically.

- 2026-07-15 map redesign + neighborhood summary + GeoJSON export:
  - User's Neighborhoods.shp (51 polygons, SAME CRS as parcels: NAD83 Iowa South
    State Plane ft, ESRI:102676) -> `nbhd_util.py` (dependency-free polygon
    shapefile reader, even-odd point-in-polygon, vertex simplification, centroid,
    pyproj WGS84 reprojection). Config: `neighborhoods_shp`.
  - `90_map_data.py` now assigns each located project to a neighborhood (PIP) and
    rolls up TIF/cost/net-gain/assessed by neighborhood. 93/107 projects fall in a
    recognized neighborhood. Top: Downtown ($58M TIF, 34 proj), Historic East
    Village ($24.6M, 18), McKinley/Columbus Park, North of Grand, Highland/Oak Pk.
  - Map artifact redesigned: neighborhood-boundary choropleth basemap (shade by
    TIF/#projects/net-gain), labels, project points (color by TIF/status/type),
    click-to-zoom neighborhoods, refined NTONTAN styling. Real geography instead
    of floating dots. Still self-contained Canvas (artifact CSP blocks tiles).
  - `95_geo_export.py` writes standard WGS84 GeoJSON to data/outputs/geo/:
    tif_projects.geojson (107 pts), tif_neighborhoods.geojson (51 polys + stats),
    tif_districts.csv — usable directly in ArcGIS.
  - pyproj installed for reprojection (ESRI:102676 -> EPSG:4326; note plain
    EPSG:102676 is NOT recognized by proj — use ESRI: or EPSG:3418).
  - Still could not visually verify render (browser pane gated); data + geometry
    + structure validated mechanically.

- 2026-07-16 GIS exports + website bundle + neighborhood breakdown:
  - Neighborhood boundaries: user's `~/Downloads/Neighborhoods.zip` (51 polygons,
    field NHNAME, SAME CRS as the parcels — NAD83 Iowa South State Plane US-ft),
    unzipped to scratchpad; path in config `neighborhoods_shp`. `nbhd_util.py`
    adds a dependency-free polygon-shapefile reader, point-in-polygon, vertex
    thinning, centroid, and ESRI:102676 -> EPSG:4326 reprojection (note: plain
    EPSG:102676 is NOT in proj's db; use ESRI:102676 or EPSG:3418).
  - `90_map_data.py` assigns each located project to a neighborhood by PIP and
    rolls up per-neighborhood stats. 93/107 land in a recognized neighborhood
    (14 are outside any). 17 of 51 neighborhoods received TIF.
  - `95_geo_export.py` (rewritten, uses pyshp) now writes ArcGIS-native
    SHAPEFILES in the source State Plane CRS + copied .prj — aligns with the
    user's own layers with no reprojection — plus WGS84 GeoJSON, a district CSV
    and `tif_fields.csv` (field dictionary; shapefile DBF names capped at 10 ch).
  - `96_neighborhood_report.py` -> per-neighborhood HTML + neighborhoods_summary
    .csv + projects_by_neighborhood.csv. Downtown 34 projects/$58.0M TIF on
    $597M cost (9.7%); Historic East Village 18/$24.6M (8.0%).
  - Templates moved into `templates/` (dashboard, map, neighborhoods) so HTML
    builds are reproducible; `91_build_map.py` injects the map; `97_build_web.py`
    builds the whole bundle -> data/outputs/web/ (index, dashboard, map,
    neighborhoods). All four verified self-contained: 0 external assets.
  - Map UX: layers are now independent toggles (shading / projects / labels /
    parcel-heat) with metric sub-selectors + "Clear all", so everything can be
    switched off to leave the bare neighborhood layout. Also fixed dot occlusion
    (draw largest-first, 78% alpha) and label crowding (top-12 always, rest at
    zoom>2.2).

- 2026-07-16 methodology page added to the web bundle:
  - `templates/methodology.html` + `build_methodology()` in `97_build_web.py`.
    Documents sources, the pipeline, the judgment calls (NPV-not-cash, never
    estimate, batch rows excluded, developer-level actual rebates), the two
    independent validations, the limitations, a glossary, and reproducibility.
  - IMPORTANT: every figure on the page is INJECTED from the pipeline's own
    outputs (projects.json, screen_stats.json, iowa_tif.json, map_data.json,
    download_log.csv) — no hardcoded numbers, so the page can't drift on rebuild.
  - The crosswalk claim is now stated as "N of M agree" with both numerator and
    denominator injected, and the wording flips automatically if agreement ever
    breaks (currently 65/65 = 100%). Don't hardcode a "100%" claim here.
  - Bundle is now 5 self-contained HTMLs (index, dashboard, map, neighborhoods,
    methodology); index links all four views.

- 2026-07-16 mobile support across the web bundle:
  - TWO STRUCTURAL BUGS found, not just styling:
    (1) the pages had NO viewport meta — templates are authored as fragments
        (<title>/<style>/markup/<script>) for Artifact preview, which supplies its
        own shell, so the standalone files were shipping without doctype/head and
        phones laid them out at ~980px. New `web_util.wrap_page()` lifts
        <title>/<style> into a real <head> (+ charset, viewport, color-scheme) and
        is applied by 70/91/96/97. Keep templates as fragments; wrap at build.
    (2) the map only had mouse handlers — pan/zoom was impossible on touch.
        Added touchstart/move/end: one finger pans, two-finger pinch zooms
        (anchored on the pinch midpoint), tap opens a project popup.
  - Map mobile layout (<=820px): stacks map (62vh) over the neighborhood ranking
    (was display:none — mobile users lost the whole by-neighborhood story);
    controls collapse to a "Layers" disclosure (auto-collapsed on narrow, via
    matchMedia); popup pinned to the bottom; bigger touch targets.
  - Dashboard (17 cols) + neighborhoods tables: on <=760px each row becomes a
    card via data-label attributes + td::before, so no horizontal scrolling.
    data-labels are injected into the row templates — if a column is added,
    ADD ITS LABEL TOO or the card view mislabels (a build assert checks count).
  - All 5 pages verified: doctype + viewport + charset + media queries, 0 external
    assets.

- 2026-07-16 METRO WORK MOVED OUT: the 12-city comparison now lives in the sibling
  project `../dsm_metro_tif/` (standalone: own config/common/web_util, own copy of
  the Iowa CSVs, own templates + outputs). Removed from THIS project: 92_metro_tif.py,
  templates/metro.html, data/interim/metro_tif.json, data/outputs/metro_tif_*.csv,
  web/metro.html, and the metro card/build block in 97_build_web.py. This pipeline is
  Des Moines project-level only — keep it that way. The notes below are retained
  because the FEASIBILITY findings matter for any future "do city X" request.

- 2026-07-16 metro comparison — Des Moines + 11 suburbs (now in ../dsm_metro_tif):
  - FEASIBILITY (important for any future "do city X" request): the pipeline has
    3 layers and they DON'T transfer equally.
      * Iowa DOM 779/1002 — covers EVERY Iowa city. Transfers free. Already had
        the CSVs; no new download needed.
      * Polk assessor — covers 10 of 12. Waukee is DALLAS county (0 parcels),
        Norwalk is WARREN (9). WDM/Urbandale/Grimes/Clive also extend into Dallas
        so their assessed totals are PARTIAL. Flagged per-city in the output.
      * Council documents — Des Moines ONLY. councildocs.dsm.city is a static,
        date-predictable PDF archive AND its staff reports carry a standardized
        FISCAL IMPACT section (NPV incentive, project cost, taxes with/without).
        Suburbs each run their own agenda system (WDM = paginated CivicPlus-style
        calendar) and don't share that fiscal-report convention — so project-level
        detail (developer, cost, net public gain, votes) is NOT portable without a
        custom harvester per city, and may not exist in comparable form at all.
  - `92_metro_tif.py` builds the actuals comparison: FY2012-24, 12 cities,
    $1.301B collected / $367M rebated. Outputs metro_tif.json + 3 CSVs
    (by_city, by_year, recipients) + templates/metro.html -> web/metro.html.
  - Finding: rebate share varies wildly — Des Moines 49.3%, Johnston 30.2%,
    Clive 35.9% vs West Des Moines 12.1%, Pleasant Hill 4.2%, Windsor Heights
    1.3%. Grimes shows 139% (rebated more than collected in-period — timing/debt,
    worth a look). WDM captures $209M (2nd most) but rebates least of the big
    cities — it spends increment on infrastructure/debt instead.
  - The metro page states the project-level gap explicitly in its footer.

- 2026-07-15 added social card (stage 95):
  - `95_social_card.py` renders data/outputs/social/dsm_tif_linkedin.png
    (1200x627, LinkedIn link-preview ratio) via matplotlib. Purpose-designed
    summary card rather than a dashboard screenshot — a 17-column table is
    unreadable at feed size. NTONTAN brand: MORTAR ground, HEAT rule + accent.
  - All figures pulled live from projects.json / iowa_tif.json so the card can't
    drift from the data. Deliberately labels its TWO periods separately: the
    money figures are Iowa state filings FY2012-24; the council record is the
    config window (2016-2026). Conflating them would misstate both.
  - matplotlib gotchas: Text has no `letterspacing` kwarg (fake it with spaces);
    set ylim headroom or the legend collides with the bars; keep the text column
    left of x=0.60 or it runs under the chart.

## Known limitations / notes for next run

- Housing Agency meetings (mg/ms) not yet harvested (v2 per spec).
- Consent Action Packets (corrections/) not harvested.
- Some 2026 items lack minutes (meeting minutes not yet posted) — dispositions
  null, will resolve on a future re-run (downloads are cached; delete the
  agenda/minutes PDF to force refresh).
- "Figure not in source" rows usually mean the number lives only in the signed
  agreement/resolution exhibit — pull from /resolutions/ or records request.
- The 2026-04-15 agenda appears to be a rescheduled 2026-04-20 meeting; both
  dates exist as documents and are reconciled by project clustering.
