import json, os, threading
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = Path(os.getenv("SUB_DATA", ROOT / "data"))
JOBS = DATA / "jobs"
FONTS = ROOT / "fonts"
for _p in (DATA, JOBS):
    _p.mkdir(parents=True, exist_ok=True)

LANGS = {
    "ar": "Arabic (literary Modern Standard Arabic)",
    "en": "English",
    "ja": "Japanese",
}
LOCK = threading.RLock()


def read_json(path, default):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return default


def write_json(path, obj):
    path = Path(path)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with LOCK:
        tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=1), encoding="utf-8")
        os.replace(tmp, path)


SETTINGS_FILE = DATA / "settings.json"
DEFAULT_SETTINGS = {"budget_usd": 1.33, "spent_usd": 0.0, "stagger_seconds": 0.4, "max_workers": 24}


def get_settings():
    s = dict(DEFAULT_SETTINGS)
    s.update(read_json(SETTINGS_FILE, {}))
    return s


def update_settings(**kw):
    with LOCK:
        s = get_settings()
        s.update(kw)
        write_json(SETTINGS_FILE, s)
        return s


def add_spent(usd):
    with LOCK:
        s = get_settings()
        s["spent_usd"] = round(s["spent_usd"] + usd, 6)
        write_json(SETTINGS_FILE, s)
