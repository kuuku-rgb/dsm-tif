"""35: Download + extract Council Communications referenced by tier-1 candidates.

CC URL pattern: {base}/communications/{20YY}/{YY-NNN}.pdf
"""
import importlib
from pathlib import Path

from common import CFG, ROOT, fetch, read_jsonl

extract_mod = importlib.import_module("20_extract_text")

RAW = ROOT / CFG["paths"]["raw"] / "cc"
TXT = ROOT / CFG["paths"]["text"] / "cc"


def main():
    RAW.mkdir(parents=True, exist_ok=True)
    TXT.mkdir(parents=True, exist_ok=True)
    cands = read_jsonl(ROOT / CFG["paths"]["interim"] / "candidates.jsonl")
    cc_nos = sorted({cc for c in cands if c["tier"] == 1 for cc in c["cc_nos"]})
    print(f"{len(cc_nos)} unique Council Communications referenced by tier-1 candidates")
    fails = []
    for cc in cc_nos:
        year = 2000 + int(cc[:2])
        url = f"{CFG['base_url']}/communications/{year}/{cc}.pdf"
        dest = RAW / f"cc{cc}.pdf"
        status, cached = fetch(url, dest)
        if status not in ("ok", "cached"):
            fails.append((cc, status))
            print(f"  {cc}: {status}")
            continue
        extract_mod.extract_pdf(dest, TXT / f"cc{cc}.json")
    print(f"done; {len(fails)} failures: {fails if fails else ''}")


if __name__ == "__main__":
    main()
