"""55: Scan agendas/minutes for certificate-of-completion and termination events.

These are the outcome signal — which approved deals were actually built (a certificate
of completion is issued once the developer satisfies the agreement) vs. terminated.
Output: data/interim/completions.jsonl  {date, kind, entity, address, text, source}
50_reconcile.py matches these to project clusters and sets each project's `status`.
"""
import json
import re
from pathlib import Path

from common import CFG, ROOT

TXT = ROOT / CFG["paths"]["text"]

COMPLETION = re.compile(r"certificate of completion", re.I)
TERMINATION = re.compile(r"terminat\w*\s+(?:the\s+)?(?:urban renewal\s+)?development agreement"
                         r"|rescind\w*\s+.{0,30}agreement|declar\w*\s+.{0,20}default", re.I)
ENTITY = re.compile(
    r"Completion\s+to\s+(?:the\s+)?([A-Z][\w&'.\- ]+?(?:,?\s*(?:LLC|L\.?P\.?|L\.?C\.?|Inc\.?|"
    r"Company|Co\.?|Partners|Corporation|Associates|LLLP))\.?)", re.I)
ADDR = re.compile(
    r"\d{2,5}[\w\- ]*?\s(?:Street|St|Avenue|Ave|Drive|Dr|Road|Rd|Boulevard|Blvd|Court|Ct|"
    r"Place|Pl|Way|Lane|Ln|Parkway|Pkwy|Circle|Terrace)\b", re.I)


def date_from(stem):
    m = re.search(r"(\d{8})$", stem)
    if not m:
        return None
    d = m.group(1)
    return f"{d[:4]}-{d[4:6]}-{d[6:8]}"


def main():
    events, seen = [], set()
    # agendas carry the descriptive wording; minutes confirm disposition
    for f in sorted(TXT.glob("ag*.json")) + sorted(TXT.glob("as*.json")):
        d = json.loads(f.read_text(encoding="utf-8"))
        date = date_from(f.stem)
        pages = d.get("pages", [])
        for pno, ptext in enumerate(pages, 1):
            lines = ptext.split("\n")
            for i, line in enumerate(lines):
                is_c = COMPLETION.search(line)
                is_t = TERMINATION.search(line)
                if not (is_c or is_t):
                    continue
                ctx = " ".join(lines[i:i + 3]).strip()
                key = (date, ctx[:90])
                if key in seen:
                    continue
                seen.add(key)
                ent = ENTITY.search(ctx)
                addr = ADDR.search(ctx)
                events.append({
                    "date": date,
                    "kind": "completion" if is_c else "termination",
                    "entity": ent.group(1).strip() if ent else None,
                    "address": addr.group(0).strip() if addr else None,
                    "text": ctx[:200],
                    "source": f.name, "page": pno,
                })
    out = ROOT / CFG["paths"]["interim"] / "completions.jsonl"
    with open(out, "w", encoding="utf-8") as fo:
        for e in events:
            fo.write(json.dumps(e, ensure_ascii=False) + "\n")
    n_c = sum(1 for e in events if e["kind"] == "completion")
    print(f"{len(events)} events ({n_c} completions, {len(events) - n_c} terminations); "
          f"{sum(1 for e in events if e['entity'])} w/ entity, "
          f"{sum(1 for e in events if e['address'])} w/ address -> {out}")


if __name__ == "__main__":
    main()
