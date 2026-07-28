"""45: Parse the 'estimated taxes with/without project' tables from Council Communications.

Each staff report's FISCAL IMPACT section carries a table:
    Sum N Years  <taxes_without>  <taxes_with>  <incentive_paid>  <net_received>
where net_received = taxes_with - incentive_paid. The public's net gain vs. doing
nothing = net_received - taxes_without. We capture per-horizon rows keyed by CC number.

Output: data/interim/fiscal_tables.json  { "YY-NNN": {horizons:{10:{...}}, ...} }
"""
import json
import re
from pathlib import Path

from common import CFG, ROOT

TXT_CC = ROOT / CFG["paths"]["text"] / "cc"

# "Sum 10 Years $224,545 $1,205,688 $300,000 $905,688"
ROW_RE = re.compile(
    r"Sum\s+(\d+)\s+Years?\s+"
    r"\$?([\d,]+)\s+\$?([\d,]+)\s+\$?([\d,]+)\s+\$?([\d,]+)", re.I)
# guard: only trust rows that sit under a with/without-project header
HEADER_RE = re.compile(r"Received without\s+.*?Received with|without\s+Project.*?with\s+Project", re.I | re.S)


def num(s):
    return int(s.replace(",", ""))


def parse_cc(text):
    if not HEADER_RE.search(text):
        return None
    horizons = {}
    for m in ROW_RE.finditer(text):
        yrs = int(m.group(1))
        without, with_, incentive, net = (num(m.group(i)) for i in range(2, 6))
        # sanity: net should be with - incentive (allow $1k rounding); skip if wildly off
        if abs((with_ - incentive) - net) > max(2000, 0.02 * with_):
            continue
        horizons[yrs] = {
            "taxes_without_project": without,
            "taxes_with_project": with_,
            "incentive_paid": incentive,
            "net_taxes_received": net,
            "net_public_gain_vs_baseline": net - without,
        }
    return horizons or None


def main():
    out = {}
    for f in sorted(TXT_CC.glob("cc*.json")):
        cc = f.stem[2:]  # cc16-693 -> 16-693
        d = json.loads(f.read_text(encoding="utf-8"))
        text = "\n".join(d.get("pages", []))
        parsed = parse_cc(text)
        if parsed:
            out[cc] = {"horizons": parsed}
    (ROOT / CFG["paths"]["interim"] / "fiscal_tables.json").write_text(
        json.dumps(out, indent=1), encoding="utf-8")
    horizons_hist = {}
    for v in out.values():
        for h in v["horizons"]:
            horizons_hist[h] = horizons_hist.get(h, 0) + 1
    print(f"parsed fiscal tables from {len(out)} CCs; horizons available: "
          f"{dict(sorted(horizons_hist.items()))}")


if __name__ == "__main__":
    main()
