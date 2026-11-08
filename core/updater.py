"""Update from inside the site: compares your files with the latest version on GitHub, downloads only what changed,
never touches the data folder, installs new libraries, and can restart the site."""
import hashlib, io, os, subprocess, sys, threading, time, zipfile
from pathlib import Path
import httpx
from .config import ROOT

REPO = "yarafarran6-eng/Sub"
BRANCH = "main"
SKIP_DIRS = {"data", ".git", "__pycache__", ".venv", "venv", "node_modules"}


class UpdateError(Exception):
    pass


def _get(url, as_json=True, timeout=60):
    try:
        r = httpx.get(url, timeout=timeout, follow_redirects=True, headers={"User-Agent": "sub-updater", "Accept": "application/vnd.github+json"})
    except httpx.HTTPError as e:
        raise UpdateError(f"ما قدرت أتصل بـGitHub. تأكد من الإنترنت. ({type(e).__name__})")
    if r.status_code == 403 or r.status_code == 429:
        raise UpdateError("GitHub حدّ عدد الطلبات من شبكتك. انتظر ساعة وجرّب، أو حدّث بملف update.bat.")
    if r.status_code == 404:
        raise UpdateError("ما لقيت المستودع على GitHub (ممكن صار خاص أو تغيّر اسمه).")
    if r.status_code != 200:
        raise UpdateError(f"GitHub رد برمز {r.status_code}")
    return r.json() if as_json else r.content


def _api_tree():
    return _get(f"https://api.github.com/repos/{REPO}/git/trees/{BRANCH}?recursive=1")


def _api_commit():
    return _get(f"https://api.github.com/repos/{REPO}/commits/{BRANCH}")


def _download_zip():
    return _get(f"https://github.com/{REPO}/archive/refs/heads/{BRANCH}.zip", as_json=False, timeout=180)


def _skip(rel):
    parts = rel.split("/")
    return parts[0] in SKIP_DIRS or any(p in SKIP_DIRS or p.startswith(".") for p in parts) or rel.endswith(".pyc")


def blob_sha(path):
    b = Path(path).read_bytes()
    return hashlib.sha1(b"blob %d\0" % len(b) + b).hexdigest()


def check():
    """-> {"changed": [...], "new": [...], "latest": {"message","date"}, "up_to_date": bool}"""
    tree = _api_tree()
    if tree.get("truncated"):
        raise UpdateError("قائمة الملفات على GitHub كبيرة جداً للفحص السريع. حدّث بملف update.bat.")
    changed, new = [], []
    for it in tree.get("tree", []):
        if it.get("type") != "blob" or _skip(it["path"]):
            continue
        local = ROOT / it["path"]
        if not local.exists():
            new.append(it["path"])
        elif blob_sha(local) != it["sha"]:
            changed.append(it["path"])
    c = _api_commit()
    info = {"message": (c.get("commit", {}).get("message") or "").split("\n")[0], "date": c.get("commit", {}).get("committer", {}).get("date", "")[:10]}
    return {"changed": sorted(changed), "new": sorted(new), "latest": info, "up_to_date": not changed and not new}


def apply(res=None):
    """Downloads the latest version and writes only the files that differ. Returns a report dict."""
    res = res or check()
    todo = set(res["changed"]) | set(res["new"])
    if not todo:
        return {"written": [], "pip": "", "needs_restart": False}
    data = _download_zip()
    try:
        z = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile:
        raise UpdateError("الملف اللي نزل من GitHub تالف. جرّب مرة ثانية.")
    written = []
    names = z.namelist()
    top = names[0].split("/")[0] + "/" if names else ""
    for rel in sorted(todo):
        member = top + rel
        if member not in names or ".." in rel.split("/") or rel.startswith("/"):
            continue
        dst = (ROOT / rel).resolve()
        if ROOT.resolve() not in dst.parents:
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        tmp = dst.with_name(dst.name + ".new")
        tmp.write_bytes(z.read(member))
        os.replace(tmp, dst)
        written.append(rel)
    pip = ""
    if "requirements.txt" in written:
        try:
            r = subprocess.run([sys.executable, "-m", "pip", "install", "-r", str(ROOT / "requirements.txt")], capture_output=True, text=True, timeout=600)
            pip = "ثُبّتت المكتبات الجديدة" if r.returncode == 0 else "تعذّر تثبيت مكتبات جديدة: " + (r.stderr or r.stdout)[-200:]
        except Exception as e:
            pip = f"تعذّر تثبيت مكتبات جديدة: {e}"
    return {"written": written, "pip": pip, "needs_restart": any(w.endswith(".py") or w.endswith(".css") or w.endswith(".js") for w in written)}


def restart(delay=1.5):
    """Starts a new copy of the site after this one exits, then exits. The browser page reloads itself (see settings tab)."""
    args = [sys.executable] + sys.argv
    code = ("import subprocess,sys,time,os; time.sleep(3); "
            f"kw = dict(cwd={str(ROOT)!r}); "
            "kw['creationflags'] = 0x10 if os.name == 'nt' else 0; "
            f"subprocess.Popen({args!r}, **kw)")
    kw = {"close_fds": True}
    if os.name == "nt":
        kw["creationflags"] = 0x00000008 | 0x00000200      # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
    else:
        kw["start_new_session"] = True
    subprocess.Popen([sys.executable, "-c", code], **kw)
    threading.Timer(delay, lambda: os._exit(0)).start()
