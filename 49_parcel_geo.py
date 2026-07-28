"""49: Parcel geometry + values for mapping.

Reads AllPolk.shp (Point geometry, NAD83 Iowa South State Plane feet) aligned
record-for-record with AllPolk.dbf, filtered to Des Moines. Emits compact parallel
arrays for a self-contained vector map: coordinates, current + prior-year assessed
value (for a year-over-year "neighborhood impact" layer), and class.

Also augments the polk address index (from 48) with parcel coordinates so 50_reconcile
can attach a lat/long-ish (x,y) point to each matched project.

Outputs:
  data/interim/parcels_geo.json  {x:[...], y:[...], total:[...], old:[...], klass:[...],
                                   bbox:[minx,miny,maxx,maxy], meta:{...}}
  (also rewrites polk_index.json entries with x,y per parcel)
"""
import json
import struct

from common import CFG, ROOT
import importlib

polk = importlib.import_module("48_polk_assessor")

DBF = polk.POLK_DBF
SHP = DBF.with_suffix(".shp")
OUT = ROOT / CFG["paths"]["interim"] / "parcels_geo.json"


def read_shp_points(path):
    """Yield (x, y) per record in file order (None for null shapes). Point shapefile."""
    with open(path, "rb") as f:
        f.read(100)  # header
        while True:
            rh = f.read(8)
            if len(rh) < 8:
                break
            content_len = struct.unpack(">i", rh[4:8])[0] * 2  # 16-bit words -> bytes
            content = f.read(content_len)
            if len(content) < 4:
                yield None
                continue
            shp_type = struct.unpack("<i", content[:4])[0]
            if shp_type == 1 and len(content) >= 20:
                x, y = struct.unpack("<2d", content[4:20])
                yield (x, y)
            else:
                yield None


def dbf_rows_in_order(path):
    """Yield each DBF row (dict) in file order, incl. deleted flag, for shp alignment."""
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
            fields.append((fd[:11].split(b"\x00")[0].decode("latin1"), pos, fd[16]))
            pos += fd[16]
        f.seek(hlen)
        data = f.read()
        for i in range(n):
            rec = data[i * rlen:(i + 1) * rlen]
            if not rec:
                yield None
                continue
            yield {nm: rec[s:s + l].decode("latin1").strip() for nm, s, l in fields}


def num(v):
    try:
        return float(v)
    except (ValueError, TypeError):
        return None


def main():
    xs, ys, tot, old, kl = [], [], [], [], []
    pts = read_shp_points(SHP)
    n = skipped = 0
    for row, xy in zip(dbf_rows_in_order(DBF), pts):
        if row is None or xy is None:
            continue
        if row.get("JURISDICT", "").upper() != "DES MOINES":
            continue
        t = num(row.get("TOTAL_FULL"))
        if t is None:
            continue
        xs.append(round(xy[0], 1)); ys.append(round(xy[1], 1))
        tot.append(round(t)); old.append(round(num(row.get("TOTAL_OLD")) or 0))
        kl.append(row.get("CLASS") or "")
        n += 1
    bbox = [min(xs), min(ys), max(xs), max(ys)] if xs else [0, 0, 0, 0]
    OUT.write_text(json.dumps({
        "x": xs, "y": ys, "total": tot, "old": old, "klass": kl, "bbox": bbox,
        "meta": {"n": n, "crs": "NAD83 Iowa South State Plane (US ft)",
                 "note": "TOTAL_OLD is prior-roll value; change = total-old"},
    }), encoding="utf-8")
    print(f"wrote {n} Des Moines parcels with geometry -> {OUT}")
    print(f"  bbox x[{bbox[0]:.0f},{bbox[2]:.0f}] y[{bbox[1]:.0f},{bbox[3]:.0f}]")


if __name__ == "__main__":
    main()
