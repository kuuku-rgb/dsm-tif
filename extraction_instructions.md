# Extraction instructions — DSM council candidate items → JSONL records

You are given bundle file(s). Each contains sections like:

```
## CANDIDATE 2025-05-05#item33
{metadata JSON: meeting_date, meeting_type, item_no, roll_call_no, vote, cc_nos,
 agenda_url, minutes_url, agenda_pages, minutes_pages, keywords}
### AGENDA ITEM TEXT
### MINUTES ITEM TEXT
### COUNCIL COMMUNICATION NN-NNN   (full text, with "[cc page N]" markers)
```

For EACH candidate section, emit exactly ONE minified JSON object on its own line
(JSONL). Write the full set for each bundle to the output path you were assigned,
using the Write tool, UTF-8, one record per line.

## Record schema

```json
{
  "candidate_id": "from the '## CANDIDATE' header, verbatim",
  "meeting_date": "YYYY-MM-DD",
  "meeting_type": "regular | special | housing",
  "resolution_or_item_no": "roll-call number like '25-0662' if known, else item no",
  "council_communication_no": "e.g. '25-186' | null",
  "action_type": "resolution of intent | set public hearing | approve development agreement | amend agreement | certificate of completion | ordinance | other",
  "developer_owner": "counterparty name, verbatim | null",
  "project_name": "short project name (use CC heading/synopsis wording) | null",
  "address": "project address(es) | null",
  "urban_renewal_area": "named UR area / TIF district | null",
  "tif": {
    "amount_usd": null,
    "structure": "verbatim-ish, e.g. '82% of TIF years 4-8, NPV at 4.5%' | null",
    "term_years": null
  },
  "total_project_cost_usd": null,
  "other_incentives": [
    {"type": "economic development grant | forgivable loan | tax abatement | land conveyance | revenue bond | fee waiver | grant | loan | parking | other",
     "amount_usd": null, "detail": "string | null"}
  ],
  "affordable_units": null,
  "total_units": null,
  "disposition": "approved | deferred | denied | continued | hearing set | withdrawn | null",
  "vote": "'7-0' or '6-0-1' | null",
  "recusals": "string | null",
  "source": {"url": "doc the KEY FIGURES came from", "page": 1, "anchor_quote": "<15 words verbatim"},
  "confidence": "high | medium | low",
  "flags": [],
  "notes": "ambiguities, sub-items (A)/(B)/(C), 'as set forth in agreement' | null"
}
```

## Hard rules

1. **Never fabricate a figure.** If a dollar amount / unit count / term is not stated
   in the provided text, use `null` and add flag `"figure_not_in_source"` (only when
   an agreement/incentive clearly exists but its number is absent). Do not infer,
   do not compute (exception: you may sum explicitly itemized sub-amounts only if
   the text presents them as parts of one incentive — otherwise report in
   other_incentives separately).
2. **TIF vs other incentives:** put an incentive under `tif` only when the text ties
   the payment to tax increment (TIF rebate, % of increment, increment-backed grant
   or forgivable loan). A forgivable loan sized by TIF NPV (e.g. "equivalent to 82%
   of project generated TIF") goes in BOTH: other_incentives (forgivable loan,
   amount) and tif.structure describing the increment basis; put the loan amount in
   tif.amount_usd only if the text itself calls it a TIF payment/rebate. When unsure,
   put the amount in other_incentives and describe in notes.
3. **Figures priority:** Council Communication > agenda text > minutes.
   `source.url`: CC URL is `https://councildocs.dsm.city/communications/20YY/YY-NNN.pdf`
   (20YY from the CC number prefix). `source.page` = the `[cc page N]` marker.
   If figures came from the agenda, use the agenda_url and agenda_pages[0].
4. **Disposition** from MINUTES text: "Moved ... to adopt ... Motion Carried" →
   approved; "WITHDRAWN" → withdrawn; "continued"/"deferred to" → continued;
   "hearing ... set"/date-setting resolutions → hearing set. Vote from "Motion
   Carried 7-0" (may be line-wrapped, e.g. "6-" / "1"). Recusals: any member noted
   as abstaining/recusing or conflict of interest.
5. **action_type:** "preliminary terms" → resolution of intent; "final terms" /
   "approving ... development agreement" → approve development agreement;
   "amendment/amended and restated" → amend agreement; "setting date of hearing" →
   set public hearing; certificate of completion → certificate of completion;
   TIF-district ordinances → ordinance.
6. If a candidate turns out NOT to be a developer/owner incentive action (e.g. plain
   right-of-way purchase, city-only bond issuance with no counterparty), still emit
   a record: action_type "other", flag `"not_incentive_related"`, nulls elsewhere.
7. Multi-part items (A)(B)(C): ONE record for the item; describe sub-parts in notes
   and put each incentive-bearing sub-part in other_incentives.
8. **confidence:** high = figures + counterparty + disposition all explicit;
   medium = agreement clear but some fields missing; low = ambiguous item.
9. Numbers are plain JSON numbers: $12,355,000 → 12355000. No strings, no commas.
10. anchor_quote: under 15 words, verbatim, containing or adjacent to the headline
    figure (or the item title if no figure).

Return (as your final message) only: the bundle name(s), record count written, and
any candidates you could not process.
