"""91: Inject map_data.json into the map template -> data/outputs/web/map.html"""
import json

from common import CFG, ROOT
from web_util import wrap_page

TPL = ROOT / "templates" / "map.html"
OUT = ROOT / CFG["paths"]["outputs"] / "web" / "map.html"


def main():
    OUT.parent.mkdir(parents=True, exist_ok=True)
    data = (ROOT / CFG["paths"]["interim"] / "map_data.json").read_text(encoding="utf-8")
    tpl = TPL.read_text(encoding="utf-8")
    assert "__MAPDATA__" in tpl, "template missing __MAPDATA__"
    OUT.write_text(wrap_page(tpl.replace("__MAPDATA__", data)), encoding="utf-8")
    md = json.loads(data)
    print(f"wrote {OUT} ({md['meta']['mapped']} mapped projects, "
          f"{md['meta']['n_nbhds']} neighborhoods)")


if __name__ == "__main__":
    main()
