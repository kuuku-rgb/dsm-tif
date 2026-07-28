"""46: Extract the net-present-value (NPV) TIF incentive per Council Communication.

Des Moines staff reports state TIF assistance two ways: a larger "cash basis" (nominal
sum of rebates over the term) and a smaller "net present value" (NPV, discounted). The
city's COMMITTED, capped obligation and its published "% of total project cost" both use
the NPV. Structured extraction sometimes captured the cash figure, overstating the
incentive by 40-75%. This stage recovers the canonical NPV from each CC so 50_reconcile
can standardize every project's TIF amount on the same (NPV) basis.

Output: data/interim/tif_npv.json  { "YY-NNN": {"npv": int|null, "method": str,
                                                  "cash": [int,...]} }
"""
import json
import re

from common import CFG, ROOT

TXT_CC = ROOT / CFG["paths"]["text"] / "cc"
NPV_CUE = r"(?:net present value|\bNPV\b|on a NPV)"
AMT = r"\$\s?([\d,]+(?:\.\d+)?)\s*(million|M\b)?"


def to_num(s, unit):
    v = float(s.replace(",", ""))
    if unit and unit.lower().startswith("m"):
        v *= 1e6
    return round(v)


def _amounts_before_cue(text, cue):
    """Dollar amounts immediately followed (<=45 chars, no sentence break) by `cue`."""
    out = []
    for m in re.finditer(AMT, text):
        tail = text[m.end():m.end() + 45]
        if re.match(r"[^.$]*?" + cue, tail, re.I):
            out.append(to_num(m.group(1), m.group(2)))
    return out


CAP_RE = re.compile(
    r"capp?ed maximum amount of assistance (?:at|of)\s*" + AMT, re.I)


def _caps(t):
    """'capped maximum amount of assistance at $X ... net present value' figures.

    The cap IS the committed NPV obligation; a CC states one cap per phase. This must
    take priority over a raw NPV-amount sweep, which would also pick up the cap's own
    'estimated $Y NPV' and double-count them as two phases.
    """
    out = []
    for m in CAP_RE.finditer(t):
        if re.search(NPV_CUE, t[m.end():m.end() + 60], re.I):
            out.append(to_num(m.group(1), m.group(2)))
    return out


def npv_for_text(t):
    caps = _caps(t)
    if caps:
        vals = sorted(set(caps))
        return sum(vals), ("capped max" if len(vals) == 1 else f"sum of {len(vals)} phase caps")
    # explicit "total ... $X ... NPV" (already the cross-phase sum)
    mt = re.search(r"total[^.$]{0,30}\$\s?([\d,]+(?:\.\d+)?)\s*(million|M\b)?[^.$]{0,20}" + NPV_CUE,
                   t, re.I)
    if mt:
        return to_num(mt.group(1), mt.group(2)), "explicit total"
    npv_vals = _amounts_before_cue(t, NPV_CUE)
    if not npv_vals:
        return None, "none"
    cash_vals = _amounts_before_cue(t, r"cash basis")
    cand = min(npv_vals)
    # NPV can never exceed the nominal/cash sum; if a smaller cash-labeled figure
    # exists, the CC's NPV/cash labels are reversed (a known staff-report error) —
    # take the smaller figure as the true NPV.
    if cash_vals and min(cash_vals) < cand:
        return min(cash_vals), "min(npv,cash) — reversed labels in source"
    if len(set(npv_vals)) == 1:
        return cand, "single"
    return sum(sorted(set(npv_vals))), f"sum of {len(set(npv_vals))} phase NPVs"


def main():
    out = {}
    for f in sorted(TXT_CC.glob("cc*.json")):
        cc = f.stem[2:]
        t = " ".join(json.loads(f.read_text(encoding="utf-8")).get("pages", []))
        npv, method = npv_for_text(t)
        cash = sorted(set(_amounts_before_cue(t, r"cash basis")))
        if npv is not None or cash:
            out[cc] = {"npv": npv, "method": method, "cash": cash}
    (ROOT / CFG["paths"]["interim"] / "tif_npv.json").write_text(
        json.dumps(out, indent=1), encoding="utf-8")
    n_npv = sum(1 for v in out.values() if v["npv"])
    print(f"parsed {len(out)} CCs; {n_npv} with an NPV incentive figure -> tif_npv.json")


if __name__ == "__main__":
    main()
