"""10: Download agenda + minutes PDFs for every meeting -> data/raw/; cached, polite."""
from pathlib import Path

import pandas as pd

from common import CFG, ROOT, fetch

RAW = ROOT / CFG["paths"]["raw"]


def main():
    meetings = pd.read_csv(ROOT / CFG["paths"]["interim"] / "meetings.csv")
    log = []
    for _, m in meetings.iterrows():
        for col in ("agenda_url", "minutes_url"):
            url = m[col]
            if not isinstance(url, str):
                continue
            dest = RAW / url.rsplit("/", 1)[1]
            status, cached = fetch(url, dest)
            log.append({"meeting_date": m.meeting_date, "doc": col, "url": url, "status": status})
            if not cached:
                print(f"{m.meeting_date} {col}: {status}")
    dl = pd.DataFrame(log)
    dl.to_csv(ROOT / CFG["paths"]["interim"] / "download_log.csv", index=False)
    bad = dl[~dl.status.isin(["ok", "cached"])]
    print(f"\n{len(dl)} docs; {len(bad)} failures")
    if len(bad):
        print(bad.to_string(index=False))


if __name__ == "__main__":
    main()
