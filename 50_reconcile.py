"""50: Cluster tier-1 records into projects, build timelines, pick headline rows.

Inputs : data/interim/records.jsonl   (Claude-extracted tier-1 records, schema §6)
         data/interim/candidates.jsonl (all screened items; tier-2 go to actions log)
Outputs: data/interim/projects.json    (clustered, with timeline + headline terms)
         data/interim/actions_long.csv (every screened council action)
"""
import json
import re
from difflib import SequenceMatcher

import importlib

import pandas as pd

from common import CFG, ROOT, read_jsonl

polk = importlib.import_module("48_polk_assessor")

INTERIM = ROOT / CFG["paths"]["interim"]

ABBREV = {"avenue": "ave", "avenues": "ave", "street": "st", "streets": "st",
          "drive": "dr", "boulevard": "blvd", "road": "rd", "court": "ct",
          "parkway": "pkwy", "place": "pl",
          "east": "e", "west": "w", "north": "n", "south": "s",
          "southeast": "se", "southwest": "sw", "northeast": "ne", "northwest": "nw",
          "first": "1st", "second": "2nd", "third": "3rd", "fourth": "4th",
          "fifth": "5th", "sixth": "6th", "seventh": "7th", "eighth": "8th",
          "ninth": "9th", "tenth": "10th"}


def norm(s):
    if not s:
        return ""
    s = re.sub(r"\(.*?\)", " ", s.lower())
    s = re.sub(r"[^\w\s]", " ", s)
    words = [ABBREV.get(w, w) for w in s.split()]
    return " ".join(words)


def norm_addresses(addr):
    """Split a possibly multi-address string; normalize each."""
    if not addr:
        return set()
    parts = [norm(p) for p in re.split(r"[;,]| and ", re.sub(r"\(.*?\)", " ", addr))]
    out = set()
    for i, p in enumerate(parts):
        if re.fullmatch(r"\d+", p):
            # bare street number from "606 and 666 Walnut St" — borrow the street name
            for q in parts[i + 1:]:
                m = re.match(r"\d+\s+(.+)", q)
                if m:
                    out.add(f"{p} {m.group(1)}")
                    break
        elif re.search(r"\d", p) and len(p) > 5:
            out.add(p)
    return out


GENERIC_BIGRAMS = {"mixed use", "urban renewal", "development agreement",
                   "des moines", "apartment building", "housing project",
                   "commercial property", "master development"}


def name_bigrams(name):
    words = norm(name).split()
    return {" ".join(words[i:i + 2]) for i in range(len(words) - 1)} - GENERIC_BIGRAMS


def similar(a, b):
    return SequenceMatcher(None, a, b).ratio() if a and b else 0.0


WHTC_BATCH_RE = re.compile(
    r"workforce housing tax credit.*(applications?|support|resolutions?|benefit)", re.I)


def num_tokens(r):
    """Street-number tokens from the address; fall back to digits in the name."""
    toks = {t for a in norm_addresses(r.get("address")) for t in a.split() if t[:1].isdigit()}
    if not toks:
        toks = set(re.findall(r"\d+", norm(r.get("project_name"))))
    return toks


def dev_compatible(r1, r2):
    """True unless both records name clearly different developers (distinct deals
    at one address, e.g. successive corporate tenants of the same building)."""
    d1, d2 = norm(r1.get("developer_owner")), norm(r2.get("developer_owner"))
    if not d1 or not d2:
        return True  # missing name -> don't block a merge
    if similar(d1, d2) >= 0.55:
        return True
    # same principals sometimes appear via different LLC names -> allow only if the
    # project NAMES are strongly similar. A single shared bigram is NOT enough: it is
    # usually a shared LOCATION ("Southridge Mall", "6th Avenue") that co-locates
    # distinct deals by different developers.
    n1, n2 = norm(r1.get("project_name")), norm(r2.get("project_name"))
    if n1 and n2 and similar(n1, n2) >= 0.7:
        return True
    return False


def same_project(r1, r2):
    # annual WHTC-application batches list many unrelated projects; never cluster across meetings
    if any(WHTC_BATCH_RE.search(r.get("project_name") or "") for r in (r1, r2)):
        return False
    a1, a2 = norm_addresses(r1.get("address")), norm_addresses(r2.get("address"))
    # shared address merges only when developers are compatible — a single building can
    # host distinct deals with different developers across a 10-year window
    if a1 & a2 and dev_compatible(r1, r2):
        return True
    # differing street numbers on both sides veto fuzzy-name merges
    # (e.g. "MAA - 4205 Merle Hay Rd" vs "MAA - 4347 Merle Hay Rd")
    t1, t2 = num_tokens(r1), num_tokens(r2)
    if t1 and t2 and not (t1 & t2):
        return False
    n1, n2 = norm(r1.get("project_name")), norm(r2.get("project_name"))
    if n1 and n2 and similar(n1, n2) >= 0.85:
        return True
    # same developer + overlapping street number tokens or shared distinctive name bigram
    d1, d2 = norm(r1.get("developer_owner")), norm(r2.get("developer_owner"))
    if d1 and d2 and similar(d1, d2) >= 0.9:
        t1 = {t for a in a1 for t in a.split() if t[:1].isdigit()}
        t2 = {t for a in a2 for t in a.split() if t[:1].isdigit()}
        if t1 & t2 or (not a1 and not a2):
            return True
        if name_bigrams(r1.get("project_name")) & name_bigrams(r2.get("project_name")):
            return True
    return False


def cluster(records):
    parent = list(range(len(records)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for i in range(len(records)):
        for j in range(i + 1, len(records)):
            if same_project(records[i], records[j]):
                pi, pj = find(i), find(j)
                if pi != pj:
                    parent[pj] = pi
    groups = {}
    for i in range(len(records)):
        groups.setdefault(find(i), []).append(records[i])
    return list(groups.values())


HEADLINE_PRIORITY = {"approve development agreement": 0, "amend agreement": 1,
                     "other": 2, "resolution of intent": 3, "set public hearing": 4}

# (label, keyword regex) in precedence order
PROJECT_TYPES = [
    ("TIF district / UR plan", r"TIF District|urban renewal plan"),
    ("Commercial (MAA / abatement)", r"minimum assessment"),
    ("Mixed-use", r"mixed.use|residential and commercial|commercial and residential"),
    ("Parking", r"parking (structure|garage|lot)"),
    ("Retail / restaurant", r"grocery|restaurant|retail|department store|mall"),
    ("Industrial / warehouse", r"industrial|transloading|silo|manufactur|warehouse(?!.*(apartment|office|housing|residential|loft))"),
    ("Hotel", r"hotel(?!.*housing)"),
    ("Residential", r"apartment|housing|residential|townhome|rowhome|lofts|dwelling|LIHTC|units|office.to.housing"),
    ("Office", r"office|headquarters|HQJ"),
]


def classify_type(recs, head):
    # project names are the most reliable signal; notes only break "Other" ties
    for text in (
        " ".join(filter(None, [head.get("project_name"),
                               *(r.get("project_name") for r in recs)])),
        " ".join(filter(None, [head.get("notes"), *(r.get("notes") for r in recs)])),
    ):
        for label, pat in PROJECT_TYPES:
            if re.search(pat, text, re.I):
                return label
    return "Other"


def is_nir(r):
    return "not_incentive_related" in (r.get("flags") or [])


def pick_headline(recs):
    """Prefer the (latest) development-agreement approval; fall back by priority.
    Non-incentive records (releases, certifications) never headline a mixed cluster."""
    pool = [r for r in recs if not is_nir(r)] or recs
    return sorted(pool, key=lambda r: (
        HEADLINE_PRIORITY.get(r.get("action_type"), 2),
        # among same action type, latest meeting wins
        -(int(r["meeting_date"].replace("-", "")))))[0]


def best_value(recs, path, headline):
    """Best-available figure across cluster, preferring headline; returns (value, from_date)."""
    def get(r):
        v = r
        for k in path:
            v = (v or {}).get(k) if isinstance(v, dict) else None
        return v
    hv = get(headline)
    if hv is not None:
        return hv, headline["meeting_date"]
    for r in sorted(recs, key=lambda r: r["meeting_date"], reverse=True):
        v = get(r)
        if v is not None:
            return v, r["meeting_date"]
    return None, None


def cc_list(rec):
    """CC numbers a record cites (handles 'X; Y' / 'X, Y')."""
    raw = str(rec.get("council_communication_no") or "")
    return [c.strip() for c in raw.replace(";", ",").split(",") if c.strip()]


def pick_fiscal(recs, head, fiscal):
    """Best fiscal table for a cluster: prefer the headline record's CC, else any."""
    for r in [head] + list(reversed(recs)):
        for cc in cc_list(r):
            if cc in fiscal:
                return cc, fiscal[cc]["horizons"]
    return None, None


def match_actual_rebate(head, recs, recip_norm):
    """Match an Iowa-DOM actual-rebate recipient to this cluster by developer/project name.

    Conservative: requires a strong fuzzy match (>=0.8) or full multi-word containment,
    against the cluster's developer name or project name. Returns the recipient dict or None.
    """
    cands = set()
    for r in [head] + recs:
        for key in ("developer_owner", "project_name"):
            v = norm(r.get(key))
            if v and len(v) > 4:
                cands.add(v)
    best, best_score = None, 0.0
    for rn, rec in recip_norm:
        if len(rn) < 5:
            continue
        rtoks = set(rn.split())
        for c in cands:
            ctoks = set(c.split())
            s = similar(rn, c)
            # token containment for multiword names (e.g. "sherman associates" in dev)
            contained = len(rtoks) >= 2 and rtoks <= ctoks
            if (s >= 0.8 or contained) and max(s, 0.85 if contained else 0) > best_score:
                best, best_score = rec, max(s, 0.85 if contained else 0)
    return best


def match_completions(recs, addrs, dev_norm, completions, approval_date):
    """Find completion/termination events that plausibly belong to this cluster.

    Match on address-token overlap or a strong developer-name match; only count
    events dated on/after the cluster's first action.
    """
    first = min(r["meeting_date"] for r in recs)
    hits = []
    for e in completions:
        if not e.get("date") or e["date"] < first:
            continue
        ea = norm_addresses(e.get("address")) if e.get("address") else set()
        if ea & addrs:
            hits.append(e)
            continue
        en = norm(e.get("entity")) if e.get("entity") else ""
        if en and dev_norm and similar(en, dev_norm) >= 0.86:
            hits.append(e)
    return sorted(hits, key=lambda e: e["date"])


def main():
    records = read_jsonl(INTERIM / "records.jsonl")
    cands = read_jsonl(INTERIM / "candidates.jsonl")
    fpath = INTERIM / "fiscal_tables.json"
    fiscal = json.loads(fpath.read_text(encoding="utf-8")) if fpath.exists() else {}
    npvpath = INTERIM / "tif_npv.json"
    tif_npv = json.loads(npvpath.read_text(encoding="utf-8")) if npvpath.exists() else {}
    completions = read_jsonl(INTERIM / "completions.jsonl")
    itpath = INTERIM / "iowa_tif.json"
    iowa = json.loads(itpath.read_text(encoding="utf-8")) if itpath.exists() else {}
    recipients = iowa.get("recipients", [])
    recip_norm = [(norm(r["recipient"]), r) for r in recipients]
    polk_index = polk.load_index()

    clusters = cluster(records)
    projects = []
    for recs in clusters:
        recs = sorted(recs, key=lambda r: r["meeting_date"])
        head = pick_headline(recs)
        tif_amt, tif_from = best_value(recs, ["tif", "amount_usd"], head)
        cost, cost_from = best_value(recs, ["total_project_cost_usd"], head)
        # standardize TIF on NPV basis: the extracted amount is sometimes the (larger)
        # cash-basis figure, but the city commits to and reports the NPV. Where the CC
        # gives an NPV, use it; keep the cash figure. Only lower (never raise) the amount.
        tif_basis, tif_cash = None, None
        if tif_amt is not None:
            src = next((r for r in recs if r["meeting_date"] == tif_from
                        and (r.get("tif") or {}).get("amount_usd") == tif_amt), head)
            npv = next((tif_npv[cc]["npv"] for cc in (cc_list(src) or [c for r in recs for c in cc_list(r)])
                        if tif_npv.get(cc) and tif_npv[cc].get("npv")), None)
            if npv is None:
                tif_basis = "unverified (no NPV stated in source)"
            elif npv < tif_amt * 0.98:            # extracted a cash-basis figure -> correct down
                tif_cash, tif_amt, tif_basis = tif_amt, npv, "NPV (corrected from cash)"
            elif abs(npv - tif_amt) <= tif_amt * 0.02:
                tif_basis = "NPV (confirmed)"
            else:                                  # CC NPV exceeds extracted -> keep, note
                tif_basis = "NPV (as extracted; CC NPV differs)"
        # prefer cost from the SAME record that supplied the TIF (same project scope):
        # avoids pairing a TIF from one action with a cost from a different-scope action
        if tif_amt is not None and tif_from:
            same = next((r for r in recs if r["meeting_date"] == tif_from
                         and (r.get("tif") or {}).get("amount_usd") == tif_amt), None)
            if same and same.get("total_project_cost_usd"):
                cost, cost_from = same["total_project_cost_usd"], same["meeting_date"]
        fiscal_cc, fiscal_horizons = pick_fiscal(recs, head, fiscal)
        # outcome status: match completion/termination events to this cluster
        cl_addrs = set()
        for r in recs:
            cl_addrs |= norm_addresses(r.get("address"))
        dev_norm = norm(head.get("developer_owner"))
        comp_hits = match_completions(recs, cl_addrs, dev_norm, completions,
                                      head["meeting_date"]) if not all(is_nir(r) for r in recs) else []
        terminated = any(e["kind"] == "termination" for e in comp_hits)
        completed = any(e["kind"] == "completion" for e in comp_hits)
        status = ("terminated" if terminated else "completed" if completed else "approved")
        completion_date = next((e["date"] for e in comp_hits if e["kind"] == "completion"), None)
        actual = match_actual_rebate(head, recs, recip_norm) \
            if not all(is_nir(r) for r in recs) else None
        # Polk assessor: realized assessed value + TIF-district crosswalk (try each address)
        assessor = None
        for r in [head] + list(reversed(recs)):
            assessor = polk.match_address(polk_index, r.get("address"))
            if assessor:
                break
        all_nir = all(is_nir(r) for r in recs)
        flags = sorted({f for r in recs for f in (r.get("flags") or [])})
        devs = [norm(r.get("developer_owner")) for r in recs if r.get("developer_owner")]
        if devs and any(similar(devs[0], d) < 0.7 for d in devs[1:]):
            flags.append("counterparty_changed_across_actions")
        if not all_nir and "not_incentive_related" in flags:
            flags.remove("not_incentive_related")
        if len(recs) > 1 and "multi_meeting_project" not in flags:
            flags.append("multi_meeting_project")
        # implausible TIF-to-cost ratio => figures likely describe different scopes
        if tif_amt and cost and tif_amt > cost:
            flags.append("tif_exceeds_cost_check_scope")
        # TIF amount whose NPV basis we could not confirm (may be cash-basis, overstated)
        if tif_basis and ("unverified" in tif_basis or "differs" in tif_basis):
            flags.append("tif_basis_unverified")
        projects.append({
            "incentive_related": not all_nir,
            "project_type": classify_type(recs, head),
            "developer_owner": head.get("developer_owner"),
            "project_name": head.get("project_name") or (recs[-1].get("project_name")),
            "address": head.get("address") or next((r.get("address") for r in reversed(recs) if r.get("address")), None),
            "urban_renewal_area": next((r.get("urban_renewal_area") for r in [head] + recs[::-1] if r.get("urban_renewal_area")), None),
            "tif_amount_usd": tif_amt,
            "tif_amount_from": tif_from,
            "tif_basis": tif_basis,
            "tif_amount_cash_basis": tif_cash,
            "tif_structure": (head.get("tif") or {}).get("structure") or next(
                ((r.get("tif") or {}).get("structure") for r in recs[::-1] if (r.get("tif") or {}).get("structure")), None),
            "total_project_cost_usd": cost,
            "total_cost_from": cost_from,
            "other_incentives": head.get("other_incentives") or [],
            "affordable_units": head.get("affordable_units"),
            "total_units": head.get("total_units"),
            "final_resolution_no": head.get("resolution_or_item_no"),
            "final_action_type": head.get("action_type"),
            "final_approval_date": head["meeting_date"],
            "disposition": head.get("disposition"),
            "vote": head.get("vote"),
            "recusals": head.get("recusals"),
            "confidence": min((r.get("confidence", "low") for r in recs),
                              key=lambda c: {"high": 0, "medium": 1, "low": 2}[c]) if len(recs) == 1
                          else head.get("confidence", "low"),
            "flags": flags,
            "source_url": (head.get("source") or {}).get("url"),
            "source_page": (head.get("source") or {}).get("page"),
            "anchor_quote": (head.get("source") or {}).get("anchor_quote"),
            "n_actions": len(recs),
            "status": status,
            "completion_date": completion_date,
            "actual_rebate_paid": actual["actual_rebate_paid"] if actual else None,
            "actual_rebate_recipient": actual["recipient"] if actual else None,
            "actual_rebate_fy": [actual["fy_first"], actual["fy_last"]] if actual else None,
            "assessor_realized_total": assessor["realized_total"] if assessor else None,
            "assessor_realized_bldg": assessor["realized_bldg"] if assessor else None,
            "assessor_year_built": assessor["year_built"] if assessor else None,
            "assessor_tif_district": assessor["tif_district"] if assessor else None,
            "assessor_parcels": assessor["n_parcels"] if assessor else None,
            "x": assessor["x"] if assessor else None,
            "y": assessor["y"] if assessor else None,
            "fiscal_cc": fiscal_cc,
            "fiscal_horizons": fiscal_horizons,  # {10/20/30: {taxes_without, taxes_with, incentive_paid, net_taxes_received, net_public_gain_vs_baseline}}
            "timeline": [{"date": r["meeting_date"],
                          "action": r.get("action_type"),
                          "resolution": r.get("resolution_or_item_no"),
                          "disposition": r.get("disposition")} for r in recs],
            "records": recs,
        })
    projects.sort(key=lambda p: p["final_approval_date"], reverse=True)
    (INTERIM / "projects.json").write_text(
        json.dumps(projects, indent=1, ensure_ascii=False), encoding="utf-8")

    # Actions_long: tier-1 extracted records + tier-2 screened items
    rows = []
    for r in records:
        rows.append({
            "meeting_date": r["meeting_date"], "tier": 1,
            "item_or_resolution": r.get("resolution_or_item_no"),
            "action_type": r.get("action_type"),
            "developer_owner": r.get("developer_owner"),
            "project_name": r.get("project_name"), "address": r.get("address"),
            "tif_amount_usd": (r.get("tif") or {}).get("amount_usd"),
            "total_project_cost_usd": r.get("total_project_cost_usd"),
            "disposition": r.get("disposition"), "vote": r.get("vote"),
            "confidence": r.get("confidence"),
            "flags": ";".join(r.get("flags") or []),
            "source_url": (r.get("source") or {}).get("url"),
            "summary": None,
        })
    for c in [c for c in cands if c["tier"] == 2]:
        text = (c.get("agenda_text") or c.get("minutes_text") or "").replace("\n", " ")
        rows.append({
            "meeting_date": c["meeting_date"], "tier": 2,
            "item_or_resolution": c.get("roll_call_no") or c["item_no"],
            "action_type": None, "developer_owner": None, "project_name": None,
            "address": None, "tif_amount_usd": None, "total_project_cost_usd": None,
            "disposition": None, "vote": c.get("vote"), "confidence": None,
            "flags": "tier2_screen_only;" + ",".join(c["keywords"][:3]),
            "source_url": c.get("agenda_url") or c.get("minutes_url"),
            "summary": text[:300],
        })
    df = pd.DataFrame(rows).sort_values(["meeting_date", "tier"])
    df.to_csv(INTERIM / "actions_long.csv", index=False)
    print(f"{len(records)} tier-1 records -> {len(projects)} projects; "
          f"actions_long rows: {len(df)}")


if __name__ == "__main__":
    main()
