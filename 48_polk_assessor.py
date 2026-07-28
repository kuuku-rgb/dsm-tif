"""48: Polk County assessor parcels -> realized assessed values keyed by street address.

Two user-supplied sources (paths configurable in config.yaml):
  - AllPolk.dbf  (full county roll, ~88k Des Moines parcels) — PRIMARY value source:
    LAND_FULL/BLDG_FULL/TOTAL_FULL, YEAR_BUILT, CLASS. Combined ADDRESS string.
  - POLKCOUNTY csv (commercial/TIF subset, ~6k) — SECONDARY, kept only for its
    tif_descr field (per-parcel TIF/urban-renewal district name), which the dbf lacks.

Against the staff CC valuation projections, the current assessed value shows whether a
completed project's increment materialized; tif_descr crosswalks the UR-area field.

Builds data/interim/polk_index.json: {street_key: [ {house, total, land, bldg, year,
tif_descr, klass}, ... ]}. 50_reconcile.py matches each project's address(es) here.
This module also exposes match_address() for the reconcile step. Snapshot = current roll.
"""
import importlib
import json
import re
import struct
from pathlib import Path

import pandas as pd

from common import CFG, ROOT

POLK_DBF = Path(CFG.get("polk_assessor_dbf",
                        r"C:/Users/kuuku/OneDrive/Desktop/QCT/AllPolk.dbf"))
SHP = POLK_DBF.with_suffix(".shp")
POLK_CSV = Path(CFG.get("polk_assessor_csv",
                        r"C:/Users/kuuku/OneDrive/Desktop/QCT/POLKCOUNTY - POLKCOUNTY.csv"))
INDEX = ROOT / CFG["paths"]["interim"] / "polk_index.json"

SUFFIX = {"avenue": "ave", "street": "st", "drive": "dr", "boulevard": "blvd",
          "road": "rd", "court": "ct", "parkway": "pkwy", "place": "pl", "lane": "ln",
          "circle": "cir", "terrace": "ter", "way": "way", "trail": "trl"}
DIR = {"north": "n", "south": "s", "east": "e", "west": "w",
       "northeast": "ne", "northwest": "nw", "southeast": "se", "southwest": "sw"}
ORD = {"first": "1st", "second": "2nd", "third": "3rd", "fourth": "4th", "fifth": "5th",
       "sixth": "6th", "seventh": "7th", "eighth": "8th", "ninth": "9th", "tenth": "10th"}


def norm_token(w):
    w = w.lower().strip(".")
    return DIR.get(w, SUFFIX.get(w, ORD.get(w, w)))


def street_key(dir_, street, suffix, suffix_dir=None):
    parts = [norm_token(x) for x in (dir_, street, suffix, suffix_dir) if isinstance(x, str) and x.strip()]
    return " ".join(parts)


def parse_project_address(addr):
    """Yield (street_key, house_lo, house_hi) tuples from a messy project address.

    Handles ranges ("3404-3422 Ingersoll Avenue"), lists ("200, 210, and 216 East
    Court Avenue"), and single addresses. Streets carry across list items sharing one name.
    """
    if not addr:
        return
    addr = re.sub(r"\(.*?\)", " ", addr)
    # drop trailing city/state/zip so it doesn't leak into the street name
    addr = re.sub(r",\s*(des moines|iowa|ia)\b.*$", "", addr, flags=re.I)
    addr = re.sub(r"\b\d{5}(-\d{4})?\b", "", addr)
    for seg in re.split(r";|/| and (?=\d)", addr):
        seg = seg.strip().rstrip(",")
        # house (or range/list) then street — street may start with an ordinal (3rd, 6th)
        m = re.match(r"^(\d[\d,\s\-]*?)\s+(\S.*)$", seg)
        if not m:
            continue
        nums_raw, street_raw = m.group(1), m.group(2)
        toks = street_raw.split()
        # split leading dir + trailing suffix from the street name
        d = toks[0] if toks and toks[0].lower() in DIR else None
        rest = toks[1:] if d else toks
        suf = rest[-1] if rest and rest[-1].lower().strip(".") in SUFFIX else None
        core = rest[:-1] if suf else rest
        sk = street_key(d, " ".join(core), suf)
        if not sk:
            continue
        # expand number range(s)/list
        for chunk in re.split(r"[,\s]+", nums_raw):
            chunk = chunk.strip()
            if "-" in chunk:
                a, b = chunk.split("-")[:2]
                if a.isdigit() and b.isdigit():
                    yield sk, int(a), int(b)
            elif chunk.isdigit():
                yield sk, int(chunk), int(chunk)


def read_dbf(path, jurisdiction="DES MOINES"):
    """Stream a dBASE III file, yielding dict rows for one jurisdiction. No deps."""
    with open(path, "rb") as f:
        hdr = f.read(32)
        n = struct.unpack("<I", hdr[4:8])[0]
        hlen = struct.unpack("<H", hdr[8:10])[0]
        rlen = struct.unpack("<H", hdr[10:12])[0]
        fields, pos = [], 1
        while True:
            fd = f.read(32)
            if fd[0:1] == b"\r":
                break
            name = fd[:11].split(b"\x00")[0].decode("latin1")
            flen = fd[16]
            fields.append((name, pos, flen))
            pos += flen
        f.seek(hlen)
        data = f.read()
        for i in range(n):
            rec = data[i * rlen:(i + 1) * rlen]
            if not rec or rec[0:1] == b"*":  # deleted
                continue
            row = {nm: rec[s:s + l].decode("latin1").strip() for nm, s, l in fields}
            if row.get("JURISDICT", "").upper() == jurisdiction:
                yield row


def parse_parcel_address(addr):
    """Parse a combined parcel address ('3000 SOUTH UNION ST') -> (street_key, house)."""
    if not addr:
        return None, None
    toks = addr.split()
    if not toks or not toks[0].isdigit():
        return None, None
    house = int(toks[0])
    rest = toks[1:]
    d = rest[0] if rest and rest[0].lower() in DIR else None
    core = rest[1:] if d else rest
    suf = core[-1] if core and core[-1].lower().strip(".") in SUFFIX else None
    core = core[:-1] if suf else core
    return street_key(d, " ".join(core), suf), house


def build_index():
    # secondary: tif_descr lookup from the commercial CSV, keyed (street_key, house)
    tif_lookup = {}
    if POLK_CSV.exists():
        c = pd.read_csv(POLK_CSV, low_memory=False,
                        usecols=["city", "house", "dir", "street", "suffix", "suffix_dir", "tif_descr"])
        c = c[c.city.astype(str).str.upper().str.strip() == "DES MOINES"]
        for r in c.itertuples(index=False):
            if pd.isna(r.tif_descr) or not str(r.tif_descr).strip():
                continue
            try:
                h = int(float(r.house))
            except (ValueError, TypeError):
                continue
            sk = street_key(r.dir, r.street, r.suffix, r.suffix_dir)
            if sk:
                tif_lookup[(sk, h)] = r.tif_descr

    # primary: full county roll (all Des Moines parcels), with point geometry from the
    # aligned shapefile so each parcel carries an (x, y) State Plane coordinate
    geo = importlib.import_module("49_parcel_geo")

    def num(v):
        try:
            return float(v)
        except (ValueError, TypeError):
            return None

    idx, n = {}, 0
    for row, xy in zip(geo.dbf_rows_in_order(POLK_DBF), geo.read_shp_points(SHP)):
        if row is None or row.get("JURISDICT", "").upper() != "DES MOINES":
            continue
        sk, house = parse_parcel_address(row.get("ADDRESS", ""))
        if not sk or house is None:
            continue
        idx.setdefault(sk, []).append({
            "house": house,
            "total": num(row.get("TOTAL_FULL")),
            "land": num(row.get("LAND_FULL")),
            "bldg": num(row.get("BLDG_FULL")),
            "year": int(num(row.get("YEAR_BUILT")) or 0) or None,
            "tif_descr": tif_lookup.get((sk, house)),
            "klass": row.get("CLASS") or None,
            "x": round(xy[0], 1) if xy else None,
            "y": round(xy[1], 1) if xy else None,
        })
        n += 1
    INDEX.write_text(json.dumps(idx), encoding="utf-8")
    print(f"indexed {n} Des Moines parcels on {len(idx)} streets "
          f"({len(tif_lookup)} with TIF-district tags from CSV) -> {INDEX}")


def load_index():
    return json.loads(INDEX.read_text(encoding="utf-8")) if INDEX.exists() else {}


def match_address(index, addr):
    """Aggregate assessor parcels matching a project address. Returns dict or None."""
    parcels, seen = [], set()
    for sk, lo, hi in parse_project_address(addr):
        for p in index.get(sk, []):
            if lo <= p["house"] <= hi:
                key = (sk, p["house"], p["total"])
                if key not in seen:
                    seen.add(key)
                    parcels.append(p)
    if not parcels:
        return None
    tot = [p["total"] for p in parcels if p["total"] is not None]
    xs = [p["x"] for p in parcels if p.get("x")]
    ys = [p["y"] for p in parcels if p.get("y")]
    return {
        "n_parcels": len(parcels),
        "realized_total": round(sum(tot)) if tot else None,
        "realized_land": round(sum(p["land"] for p in parcels if p["land"])) or None,
        "realized_bldg": round(sum(p["bldg"] for p in parcels if p["bldg"])) or None,
        "year_built": max((p["year"] for p in parcels if p["year"]), default=None),
        "tif_district": next((p["tif_descr"] for p in parcels if p["tif_descr"]), None),
        "class": next((p["klass"] for p in parcels if p["klass"]), None),
        "x": round(sum(xs) / len(xs), 1) if xs else None,
        "y": round(sum(ys) / len(ys), 1) if ys else None,
    }


if __name__ == "__main__":
    build_index()
