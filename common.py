"""Shared helpers for the DSM developer-agreement pipeline."""
import json
import time
from pathlib import Path

import requests
import yaml

ROOT = Path(__file__).parent


def load_config():
    with open(ROOT / "config.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


CFG = load_config()

SESSION = requests.Session()
SESSION.headers["User-Agent"] = CFG["user_agent"]


def fetch(url, dest: Path, delay=None, retries=3):
    """Download url to dest unless it already exists. Returns (status, cached)."""
    if dest.exists() and dest.stat().st_size > 2000:
        return "cached", True
    status = "error"
    for attempt in range(retries):
        try:
            r = SESSION.get(url, timeout=60)
        except requests.RequestException as e:
            status = f"error_{type(e).__name__}"
            time.sleep(3 * (attempt + 1))
            continue
        if r.status_code == 200 and r.content[:4] == b"%PDF":
            dest.write_bytes(r.content)
            status = "ok"
        else:
            status = f"http_{r.status_code}"
            if r.status_code == 404:
                break
        if status == "ok":
            break
        time.sleep(3 * (attempt + 1))
    time.sleep(delay if delay is not None else CFG["download_delay_seconds"])
    return status, False


def read_jsonl(path):
    path = Path(path)
    if not path.exists():
        return []
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def write_jsonl(path, records):
    with open(path, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
