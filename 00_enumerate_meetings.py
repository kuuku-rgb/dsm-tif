"""00: Enumerate meetings from councildocs directory listings -> data/interim/meetings.csv"""
import re
from datetime import date

import pandas as pd

from common import CFG, SESSION, ROOT

BASE = CFG["base_url"]
START = date.fromisoformat(CFG["window"]["start"])
END = date.fromisoformat(CFG["window"]["end"])


def listing_dates(folder, prefix):
    """Scrape {BASE}/{folder}/ listing for {prefix}YYYYMMDD.pdf dates."""
    html = SESSION.get(f"{BASE}/{folder}/", timeout=60).text
    dates = set()
    for m in re.finditer(rf'href="/{folder}/{prefix}(\d{{8}})\.pdf"', html, re.I):
        try:
            dates.add(date(int(m.group(1)[:4]), int(m.group(1)[4:6]), int(m.group(1)[6:8])))
        except ValueError:
            pass
    return dates


def main():
    rows = []
    for mtype, pf in CFG["meeting_types"].items():
        ag_dates = listing_dates("agendas", pf["agenda_prefix"])
        as_dates = listing_dates("minutes", pf["minutes_prefix"])
        for d in sorted(ag_dates | as_dates):
            if not (START <= d <= END):
                continue
            ymd = d.strftime("%Y%m%d")
            rows.append({
                "meeting_date": d.isoformat(),
                "meeting_type": mtype,
                "agenda_url": f"{BASE}/agendas/{pf['agenda_prefix']}{ymd}.pdf" if d in ag_dates else None,
                "minutes_url": f"{BASE}/minutes/{pf['minutes_prefix']}{ymd}.pdf" if d in as_dates else None,
            })
    df = pd.DataFrame(rows)
    out = ROOT / CFG["paths"]["interim"] / "meetings.csv"
    df.to_csv(out, index=False)
    print(f"{len(df)} meetings in window {START}..{END} -> {out}")
    print(f"  with agenda: {df.agenda_url.notna().sum()}, with minutes: {df.minutes_url.notna().sum()}")


if __name__ == "__main__":
    main()
