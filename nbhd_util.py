"""Shared helpers for polygon shapefiles (neighborhoods): reader, point-in-polygon,
simplification, and State Plane -> WGS84 reprojection.

The neighborhood shapefile shares the parcels' CRS (NAD83 Iowa South State Plane, US ft,
ESRI:102676), so its coordinates align directly with project/parcel x,y for the map and
for point-in-polygon assignment. WGS84 is only needed for GeoJSON export.
"""
import struct
from pathlib import Path

from pyproj import Transformer

from common import CFG

NBHD_SHP = Path(CFG.get("neighborhoods_shp",
                        r"C:/Users/kuuku/AppData/Local/Temp/claude/"
                        r"C--Users-kuuku-OneDrive-Desktop-R-Projects-mgo-r-starter-with-templates-"
                        r"mgo-r-raw-City-Awards/5a972635-e8fa-40aa-9f02-794aaa314dfa/scratchpad/"
                        r"nbhd/Neighborhoods.shp"))
_TO_WGS84 = Transformer.from_crs("ESRI:102676", "EPSG:4326", always_xy=True)


def to_wgs84(x, y):
    lon, lat = _TO_WGS84.transform(x, y)
    return round(lon, 6), round(lat, 6)


def read_polygons(shp_path):
    """Read a Polygon shapefile -> list of {index, rings:[[(x,y),...],...]} in file order."""
    shapes = []
    with open(shp_path, "rb") as f:
        f.read(100)
        idx = 0
        while True:
            rh = f.read(8)
            if len(rh) < 8:
                break
            clen = struct.unpack(">i", rh[4:8])[0] * 2
            content = f.read(clen)
            idx += 1
            if len(content) < 44 or struct.unpack("<i", content[:4])[0] != 5:
                shapes.append({"index": idx - 1, "rings": []})
                continue
            n_parts, n_pts = struct.unpack("<ii", content[36:44])
            parts = list(struct.unpack("<%di" % n_parts, content[44:44 + 4 * n_parts]))
            pts_off = 44 + 4 * n_parts
            pts = struct.unpack("<%dd" % (2 * n_pts), content[pts_off:pts_off + 16 * n_pts])
            bounds = parts + [n_pts]
            rings = []
            for i in range(n_parts):
                ring = [(pts[2 * j], pts[2 * j + 1]) for j in range(bounds[i], bounds[i + 1])]
                rings.append(ring)
            shapes.append({"index": idx - 1, "rings": rings})
    return shapes


def read_dbf_field(dbf_path, field):
    """Return a list (in record order) of one text field's values."""
    with open(dbf_path, "rb") as f:
        hdr = f.read(32)
        n = struct.unpack("<I", hdr[4:8])[0]
        hlen = struct.unpack("<H", hdr[8:10])[0]
        rlen = struct.unpack("<H", hdr[10:12])[0]
        cols, pos = {}, 1
        while True:
            fd = f.read(32)
            if fd[0:1] == b"\r":
                break
            nm = fd[:11].split(b"\x00")[0].decode("latin1")
            cols[nm] = (pos, fd[16]); pos += fd[16]
        s, l = cols[field]
        f.seek(hlen); data = f.read()
        return [data[i * rlen + s:i * rlen + s + l].decode("latin1").strip() for i in range(n)]


def point_in_rings(x, y, rings):
    """Even-odd point-in-polygon across all rings (holes cancel)."""
    inside = False
    for ring in rings:
        for i in range(len(ring)):
            x1, y1 = ring[i]
            x2, y2 = ring[(i + 1) % len(ring)]
            if (y1 > y) != (y2 > y):
                xint = x1 + (y - y1) / (y2 - y1) * (x2 - x1)
                if x < xint:
                    inside = not inside
    return inside


def simplify(ring, tol=60.0):
    """Cheap vertex thinning: keep a point only if >tol ft from the last kept one."""
    if len(ring) < 4:
        return ring
    out = [ring[0]]
    for p in ring[1:]:
        if (p[0] - out[-1][0]) ** 2 + (p[1] - out[-1][1]) ** 2 >= tol * tol:
            out.append(p)
    if out[-1] != ring[-1]:
        out.append(ring[-1])
    return out


def centroid(rings):
    """Area-weighted centroid of the largest ring (for label placement)."""
    big = max(rings, key=lambda r: len(r)) if rings else []
    if len(big) < 3:
        return None
    a = cx = cy = 0.0
    for i in range(len(big)):
        x1, y1 = big[i]; x2, y2 = big[(i + 1) % len(big)]
        cr = x1 * y2 - x2 * y1
        a += cr; cx += (x1 + x2) * cr; cy += (y1 + y2) * cr
    if a == 0:
        return (sum(p[0] for p in big) / len(big), sum(p[1] for p in big) / len(big))
    return (cx / (3 * a), cy / (3 * a))
