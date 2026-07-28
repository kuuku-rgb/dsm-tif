"""20: PDF -> per-page text JSON in data/text/. Flags pages with no extractable text."""
import json
from pathlib import Path

import pdfplumber

from common import CFG, ROOT

RAW = ROOT / CFG["paths"]["raw"]
TXT = ROOT / CFG["paths"]["text"]


def extract_pdf(pdf_path: Path, out_path: Path):
    if out_path.exists():
        return "cached"
    try:
        pages, empty = [], 0
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                t = page.extract_text() or ""
                pages.append(t)
                if not t.strip():
                    empty += 1
    except Exception as e:
        # corrupt/unreadable PDF: log a stub and re-fetch candidate, don't crash the run
        out_path.write_text(
            json.dumps({"file": pdf_path.name, "n_pages": 0, "n_empty_pages": 0,
                        "pages": [], "error": f"{type(e).__name__}: {e}"}, ensure_ascii=False),
            encoding="utf-8")
        return f"ERROR {type(e).__name__}"
    out_path.write_text(
        json.dumps({"file": pdf_path.name, "n_pages": len(pages),
                    "n_empty_pages": empty, "pages": pages}, ensure_ascii=False),
        encoding="utf-8")
    return f"{len(pages)}p" + (f" ({empty} empty -> possible scan)" if empty else "")


def main():
    TXT.mkdir(exist_ok=True, parents=True)
    for pdf_path in sorted(RAW.glob("*.pdf")):
        out = TXT / (pdf_path.stem + ".json")
        status = extract_pdf(pdf_path, out)
        if status != "cached":
            print(f"{pdf_path.name}: {status}")
    print("done")


if __name__ == "__main__":
    main()
