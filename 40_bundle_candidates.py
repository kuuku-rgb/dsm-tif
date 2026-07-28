"""40a: Bundle tier-1 candidates into batch files for Claude-Code-native extraction.

Extraction mode (A) per spec §6: Claude Code reads each bundle in-session and appends
one JSON record per candidate to data/interim/records.jsonl (schema in CLAUDE.md §6).
Each bundle = agenda item text + minutes item text + full Council Communication text.

Tier-2 candidates skip LLM extraction; 50_reconcile.py routes them to Actions_long
directly from candidates.jsonl.
"""
import json
from pathlib import Path

from common import CFG, ROOT, read_jsonl

TXT_CC = ROOT / CFG["paths"]["text"] / "cc"
BUNDLES = ROOT / CFG["paths"]["interim"] / "bundles"
PER_BATCH = 8


def cc_text(cc_no):
    p = TXT_CC / f"cc{cc_no}.json"
    if not p.exists():
        return None
    d = json.loads(p.read_text(encoding="utf-8"))
    return "\n\n".join(
        f"[cc page {i}]\n{t}" for i, t in enumerate(d["pages"], 1))


def main():
    BUNDLES.mkdir(parents=True, exist_ok=True)
    for old in BUNDLES.glob("batch_*.md"):
        old.unlink()
    # incremental: skip candidates already present in records.jsonl (stable candidate_id)
    done = {r["candidate_id"] for r in
            read_jsonl(ROOT / CFG["paths"]["interim"] / "records.jsonl")}
    cands = [c for c in read_jsonl(ROOT / CFG["paths"]["interim"] / "candidates.jsonl")
             if c["tier"] == 1
             and f"{c['meeting_date']}#item{c['item_no']}" not in done]
    print(f"skipping {len(done)} already-extracted; bundling {len(cands)} new candidates")
    batches = [cands[i:i + PER_BATCH] for i in range(0, len(cands), PER_BATCH)]
    for bi, batch in enumerate(batches, 1):
        parts = []
        for c in batch:
            cid = f"{c['meeting_date']}#item{c['item_no']}"
            parts.append(f"## CANDIDATE {cid}")
            parts.append(json.dumps({k: c[k] for k in (
                "meeting_date", "meeting_type", "item_no", "roll_call_no", "vote",
                "cc_nos", "agenda_url", "minutes_url", "agenda_pages", "minutes_pages",
                "keywords")}, ensure_ascii=False))
            parts.append(f"### AGENDA ITEM TEXT\n{c['agenda_text'] or '(none)'}")
            parts.append(f"### MINUTES ITEM TEXT\n{c['minutes_text'] or '(none)'}")
            for cc in c["cc_nos"]:
                t = cc_text(cc)
                parts.append(f"### COUNCIL COMMUNICATION {cc}\n{t or '(not retrieved)'}")
        (BUNDLES / f"batch_{bi:03d}.md").write_text("\n\n".join(parts), encoding="utf-8")
    print(f"{len(cands)} tier-1 candidates -> {len(batches)} bundles in {BUNDLES}")


if __name__ == "__main__":
    main()
