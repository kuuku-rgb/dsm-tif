"""30: Segment agendas/minutes into numbered items, keyword-screen -> data/interim/candidates.jsonl

Per candidate: agenda item block (+pages), matched keywords + tier, Council Communication
numbers, and the matching minutes block (roll-call number, vote, disposition text).
"""
import json
import re
from pathlib import Path

import pandas as pd

from common import CFG, ROOT, write_jsonl

TXT = ROOT / CFG["paths"]["text"]

# Item header: "33. Text..." or "18-I Text..." at line start (1-3 digit item numbers).
ITEM_RE = re.compile(r"^(\d{1,3})(-[IVXL]+)?\.?\s+(?=[A-Z(\"'])")
# Minutes blocks usually open with a roll-call number: "25-1278 17. Approving..."
MIN_ITEM_RE = re.compile(r"^(\d{2}-\d{4})?\s*(\d{1,3})(-[IVXL]+)?\.?\s+(?=[A-Z(\"'])")
CC_PHRASE_RE = re.compile(
    r"Council Communication Nos?\.\s*((?:\d{2}-\d{3}[\s,]*(?:and\s*)?)+)", re.I)
CC_NUM_RE = re.compile(r"\d{2}-\d{3}")


def find_cc_nos(text):
    return sorted({n for m in CC_PHRASE_RE.finditer(text)
                   for n in CC_NUM_RE.findall(m.group(1))})
VOTE_RE = re.compile(r"(?:Motion |Roll Call: )?Carried\s+(\d+-\d+(?:-\d+)?)", re.I)

TIER1 = [re.compile(k, re.I) for k in CFG["keywords"]["tier1"]]
TIER2 = [re.compile(k, re.I) for k in CFG["keywords"]["tier2"]]


def segment_items(pages, minutes=False):
    """Split a document's pages into numbered item blocks.

    Returns list of dicts: item_no, suffix, text, page_start, page_end, roll_call_no.
    """
    items = []
    cur = None
    header_re = MIN_ITEM_RE if minutes else ITEM_RE
    for pno, ptext in enumerate(pages, 1):
        for line in ptext.split("\n"):
            stripped = line.strip()
            # skip bare page-number footer lines
            if re.fullmatch(r"\d{1,3}", stripped):
                continue
            m = header_re.match(line)
            if m:
                if minutes:
                    rc, num, suf = m.group(1), m.group(2), m.group(3) or ""
                else:
                    rc, num, suf = None, m.group(1), m.group(2) or ""
                # guard against false headers: item numbers ordinarily ascend or repeat nearby
                if cur is not None:
                    items.append(cur)
                cur = {"item_no": num + suf, "roll_call_no": rc,
                       "text": line, "page_start": pno, "page_end": pno}
            elif cur is not None:
                cur["text"] += "\n" + line
                cur["page_end"] = pno
    if cur is not None:
        items.append(cur)
    return items


def screen_text(text):
    hits1 = sorted({p.pattern for p in TIER1 if p.search(text)})
    hits2 = sorted({p.pattern for p in TIER2 if p.search(text)})
    tier = 1 if hits1 else (2 if hits2 else None)
    return tier, hits1 + hits2


def load_pages(stem):
    p = TXT / f"{stem}.json"
    if not p.exists():
        return None
    return json.loads(p.read_text(encoding="utf-8"))["pages"]


def main():
    meetings = pd.read_csv(ROOT / CFG["paths"]["interim"] / "meetings.csv")
    candidates = []
    stats = {"meetings": 0, "items": 0, "tier1": 0, "tier2": 0}
    for _, mtg in meetings.iterrows():
        ymd = mtg.meeting_date.replace("-", "")
        ag_pages = load_pages(f"ag{ymd}") if isinstance(mtg.agenda_url, str) else None
        mn_pages = load_pages(f"as{ymd}") if isinstance(mtg.minutes_url, str) else None
        if ag_pages is None and mn_pages is None:
            continue
        stats["meetings"] += 1
        ag_items = segment_items(ag_pages) if ag_pages else []
        mn_items = segment_items(mn_pages, minutes=True) if mn_pages else []
        mn_by_no = {}
        for it in mn_items:
            mn_by_no.setdefault(it["item_no"], it)
        stats["items"] += len(ag_items)

        # screen agenda items (primary); fall back to minutes-only if no agenda
        base_items = ag_items if ag_items else mn_items
        for it in base_items:
            tier, hits = screen_text(it["text"])
            if tier is None:
                continue
            mn_match = mn_by_no.get(it["item_no"]) if ag_items else it
            mn_text = mn_match["text"] if mn_match else None
            vote = None
            if mn_text:
                vm = VOTE_RE.search(mn_text)
                vote = vm.group(1) if vm else None
            candidates.append({
                "meeting_date": mtg.meeting_date,
                "meeting_type": mtg.meeting_type,
                "item_no": it["item_no"],
                "tier": tier,
                "keywords": hits,
                "agenda_text": it["text"] if ag_items else None,
                "agenda_pages": [it["page_start"], it["page_end"]] if ag_items else None,
                "agenda_url": mtg.agenda_url if isinstance(mtg.agenda_url, str) else None,
                "cc_nos": sorted(set(find_cc_nos(it["text"]))
                                 | set(find_cc_nos(mn_text or ""))),
                "minutes_text": mn_text,
                "minutes_pages": [mn_match["page_start"], mn_match["page_end"]] if mn_match else None,
                "minutes_url": mtg.minutes_url if isinstance(mtg.minutes_url, str) else None,
                "roll_call_no": mn_match["roll_call_no"] if mn_match else None,
                "vote": vote,
            })
            stats[f"tier{tier}"] += 1

    out = ROOT / CFG["paths"]["interim"] / "candidates.jsonl"
    write_jsonl(out, candidates)
    (ROOT / CFG["paths"]["interim"] / "screen_stats.json").write_text(
        json.dumps(stats), encoding="utf-8")
    print(f"screened {stats['meetings']} meetings, {stats['items']} agenda items")
    print(f"candidates: tier1={stats['tier1']} tier2={stats['tier2']} -> {out}")


if __name__ == "__main__":
    main()
