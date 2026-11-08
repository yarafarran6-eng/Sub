"""In-site updater: finds changed/new files, writes only those, never touches data, no network (GitHub calls are replaced)."""
import hashlib, io, os, shutil, sys, tempfile, zipfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import warnings; warnings.filterwarnings("ignore")
from pathlib import Path
from core import updater

REAL = Path(updater.ROOT)
tmp = Path(tempfile.mkdtemp())
shutil.copytree(REAL, tmp / "site", ignore=shutil.ignore_patterns(".git", "__pycache__", "data", "fonts", "tests"))
site = tmp / "site"
(site / "data").mkdir(); (site / "data" / "keys.json").write_text("SECRET")
updater.ROOT = site

remote = {}                                              # what "GitHub" has = the real repo files (the originals)
for p in REAL.rglob("*"):
    rel = p.relative_to(REAL).as_posix()
    if p.is_file() and not updater._skip(rel) and not rel.startswith(("fonts/", "tests/")):
        remote[rel] = p.read_bytes()
remote["ui/brand_new.py"] = b"# new file\n"

(site / "core" / "chats.py").write_text("# locally old version\n")          # differs from remote
(site / "extra_local.txt").write_text("mine")                                 # only local: must survive

def sha(b): return hashlib.sha1(b"blob %d\0" % len(b) + b).hexdigest()
updater._api_tree = lambda: {"tree": [{"type": "blob", "path": k, "sha": sha(v)} for k, v in remote.items()] + [{"type": "blob", "path": "data/x.json", "sha": "0"}]}
updater._api_commit = lambda: {"commit": {"message": "test commit\nbody", "committer": {"date": "2026-11-08T10:00:00Z"}}}
buf = io.BytesIO()
with zipfile.ZipFile(buf, "w") as z:
    for k, v in remote.items(): z.writestr("Sub-main/" + k, v)
updater._download_zip = lambda: buf.getvalue()

r = updater.check()
assert r["changed"] == ["core/chats.py"] and r["new"] == ["ui/brand_new.py"], r
assert not r["up_to_date"] and r["latest"]["message"] == "test commit"
out = updater.apply(r)
assert sorted(out["written"]) == ["core/chats.py", "ui/brand_new.py"] and out["needs_restart"], out
assert (site / "core" / "chats.py").read_bytes() == remote["core/chats.py"]
assert (site / "data" / "keys.json").read_text() == "SECRET" and not (site / "data" / "x.json").exists(), "data untouched"
assert (site / "extra_local.txt").read_text() == "mine"
assert updater.check()["up_to_date"]
assert updater.apply()["written"] == []

# GitHub API blocked / rate limited -> the check still works by comparing with the downloaded zip
(site / "ui" / "brand_new.py").unlink(); (site / "core" / "chats.py").write_text("# old again\n")
def api_down(): raise updater.UpdateError("GitHub حدّ عدد الطلبات من شبكتك.")
real_tree = updater._api_tree; updater._api_tree = api_down; updater._zip_cache.clear()
r2 = updater.check()
assert r2["changed"] == ["core/chats.py"] and r2["new"] == ["ui/brand_new.py"], r2
assert len(updater.apply(r2)["written"]) == 2 and updater.check()["up_to_date"]
updater._api_tree = real_tree

# a bad path inside the answer must never write outside the folder
updater._api_tree = lambda: {"tree": [{"type": "blob", "path": "../evil.py", "sha": "1"}]}
assert updater.apply(updater.check())["written"] == []
assert not (tmp / "evil.py").exists()

# secure connection broken (filter / antivirus) -> falls back to curl; both broken -> clear message with the details
def boom(*a, **k):
    import ssl; raise ssl.SSLError("CERTIFICATE_VERIFY_FAILED")
updater.httpx.get = boom
updater._curl = lambda url, timeout: b'{"ok": 1}'
assert updater._get("https://x") == {"ok": 1}
def curl_fail(url, timeout): raise updater.UpdateError("curl رمز 6")
updater._curl = curl_fail
try:
    updater._get("https://x"); assert False
except updater.UpdateError as e:
    assert "الإنترنت" in str(e) and "CERTIFICATE_VERIFY_FAILED" in str(e) and "curl رمز 6" in str(e), e
print("updater OK")
