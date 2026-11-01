"""Manual translation projects: extract the text of a PDF (no API needed) and let a person translate it by hand."""
import shutil, time, uuid
from pathlib import Path
from . import parser
from .config import DATA, LOCK, read_json, write_json

ROOT = DATA / "manual"
ROOT.mkdir(exist_ok=True)


def _dir(pid):
    return ROOT / pid


def create(path, on_page=None):
    pid = uuid.uuid4().hex[:8]
    d = _dir(pid)
    d.mkdir(parents=True)
    shutil.copy(path, d / "source.pdf")
    t0 = time.time()
    units, info = parser.parse_pdf(str(d / "source.pdf"), None, on_page, with_images=False)
    units = [u for u in units if u["kind"] == "text"]
    write_json(d / "units.json", units)
    meta = {"id": pid, "name": Path(path).name, "pages": info["pages"], "no_text_pages": info.get("scanned_pages", []),
            "created": int(time.time()), "extract_seconds": round(time.time() - t0, 1)}
    write_json(d / "meta.json", meta)
    return pid


def load(pid):
    d = _dir(pid)
    return read_json(d / "meta.json", None), read_json(d / "units.json", [])


def save_units(pid, units):
    if _dir(pid).exists():
        write_json(_dir(pid) / "units.json", units)


def list_projects():
    out = []
    for d in sorted(ROOT.iterdir(), key=lambda x: x.stat().st_mtime, reverse=True):
        m = read_json(d / "meta.json", None)
        if m:
            _, units = load(m["id"])
            tu = [u for u in units if u.get("translate")]
            m["total"], m["done"] = len(tu), sum(1 for u in tu if u.get("tr"))
            out.append(m)
    return out


def delete(pid):
    shutil.rmtree(_dir(pid), ignore_errors=True)


def source_path(pid):
    return str(_dir(pid) / "source.pdf")
