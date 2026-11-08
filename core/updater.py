"""Update from inside the site: compares your files with the latest version on GitHub, downloads only what changed,
never touches the data folder, installs new libraries, and can restart the site."""
import hashlib, io, json, os, shutil, subprocess, sys, threading, time, urllib.parse, zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import httpx
from .config import ROOT

REPO = "yarafarran6-eng/Sub"
BRANCH = "main"
SKIP_DIRS = {"data", ".git", "__pycache__", ".venv", "venv", "node_modules"}


class UpdateError(Exception):
    pass


_zip_cache = {}


def _curl(url, timeout):
    """Second way to download: the curl.exe that comes with Windows (the same tool update.bat uses). It trusts the system certificates,
    which fixes antivirus / network filters that break Python's own secure connection."""
    exe = shutil.which("curl.exe") or shutil.which("curl")
    if not exe:
        raise UpdateError("curl غير موجود")
    r = subprocess.run([exe, "-L", "-f", "-s", "-S", "-m", str(timeout), "-H", "User-Agent: sub-updater", url], capture_output=True, timeout=timeout + 10)
    if r.returncode != 0:
        raise UpdateError((r.stderr or b"").decode("utf-8", "ignore").strip()[:200] or f"curl رمز {r.returncode}")
    return r.stdout


def _get(url, as_json=True, timeout=60):
    try:
        r = httpx.get(url, timeout=timeout, follow_redirects=True, headers={"User-Agent": "sub-updater", "Accept": "application/vnd.github+json"})
        status, body = r.status_code, r.content
    except Exception as e:                      # blocked certificate, filter, proxy...: try curl before giving up
        first = f"{type(e).__name__}: {str(e)[:120]}"
        try:
            body, status = _curl(url, timeout), 200
        except Exception as e2:
            raise UpdateError(f"ما قدرت أتصل بـGitHub. تأكد من الإنترنت. (التفاصيل: {first} | {str(e2)[:120]})")
    if status in (403, 429):
        raise UpdateError("GitHub حدّ عدد الطلبات من شبكتك.")
    if status == 404:
        raise UpdateError("ما لقيت المستودع على GitHub (ممكن صار خاص أو تغيّر اسمه).")
    if status != 200:
        raise UpdateError(f"GitHub رد برمز {status}")
    if as_json:
        try:
            return json.loads(body)
        except ValueError:
            raise UpdateError("رد GitHub غير مفهوم (ممكن شبكتك تعترض الاتصال).")
    return body


def _api_commit():
    return _get(f"https://api.github.com/repos/{REPO}/commits/{BRANCH}")


def _api_tree(tree_sha=None):
    return _get(f"https://api.github.com/repos/{REPO}/git/trees/{tree_sha or BRANCH}?recursive=1")


def _raw(ref, path):
    """One file exactly as it was at that commit (the commit id never changes, so it can never be an old cached copy)."""
    return _get(f"https://raw.githubusercontent.com/{REPO}/{ref}/{urllib.parse.quote(path)}", as_json=False)


def _download_zip(ref=None):
    ref = ref or f"refs/heads/{BRANCH}"
    c = _zip_cache.get(ref)
    if c and c[0] > time.time() - 600:                      # just downloaded for the check: do not download twice
        return c[1]
    data = _get(f"https://github.com/{REPO}/archive/{ref}.zip", as_json=False, timeout=180)
    _zip_cache[ref] = (time.time(), data)
    return data


def _blob(b):
    return hashlib.sha1(b"blob %d\0" % len(b) + b).hexdigest()


def _skip(rel):
    parts = rel.split("/")
    return parts[0] in SKIP_DIRS or any(p in SKIP_DIRS or p.startswith(".") for p in parts) or rel.endswith(".pyc")


def blob_sha(path):
    b = Path(path).read_bytes()
    return hashlib.sha1(b"blob %d\0" % len(b) + b).hexdigest()


def _check_zip():
    """When the GitHub API refuses (rate limit, filter): compare your files with the downloaded zip itself."""
    data = _download_zip()
    try:
        z = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile:
        raise UpdateError("الملف اللي نزل من GitHub تالف. جرّب مرة ثانية.")
    names = z.namelist()
    top = names[0].split("/")[0] + "/" if names else ""
    changed, new = [], []
    for n in names:
        if n.endswith("/") or not n.startswith(top):
            continue
        rel = n[len(top):]
        if _skip(rel):
            continue
        local = ROOT / rel
        if not local.exists():
            new.append(rel)
        elif local.read_bytes() != z.read(n):
            changed.append(rel)
    return {"changed": sorted(changed), "new": sorted(new), "latest": {"message": "", "date": ""}, "up_to_date": not changed and not new}


def check():
    """-> {"changed": [...], "new": [...], "latest": {"message","date"}, "up_to_date": bool, "commit": id, "expect": {path: blob id}}"""
    try:
        c = _api_commit()
        commit = c.get("sha") or ""
        info = {"message": (c.get("commit", {}).get("message") or "").split("\n")[0], "date": c.get("commit", {}).get("committer", {}).get("date", "")[:10]}
        tree = _api_tree((c.get("commit", {}).get("tree") or {}).get("sha"))
        if tree.get("truncated"):
            raise UpdateError("truncated")
        changed, new, expect = [], [], {}
        for it in tree.get("tree", []):
            if it.get("type") != "blob" or _skip(it["path"]):
                continue
            local = ROOT / it["path"]
            expect[it["path"]] = it["sha"]
            if not local.exists():
                new.append(it["path"])
            elif blob_sha(local) != it["sha"]:
                changed.append(it["path"])
        return {"changed": sorted(changed), "new": sorted(new), "latest": info, "up_to_date": not changed and not new, "commit": commit, "expect": expect}
    except UpdateError:
        return _check_zip()                           # the API refused: compare with the downloaded zip instead


def _fetch_files(todo, res):
    """-> ({path: bytes}, [paths that could not be fetched or did not match the expected content])."""
    expect, commit = res.get("expect") or {}, res.get("commit") or ""
    got = {}

    def ok(path, data):
        return path not in expect or _blob(data) == expect[path]

    if commit and expect:                                          # best way: each file by commit id, checked against its fingerprint
        def one(path):
            try:
                return path, _raw(commit, path)
            except UpdateError:
                return path, None
        with ThreadPoolExecutor(max_workers=6) as ex:
            for path, data in ex.map(one, todo):
                if data is not None and ok(path, data):
                    got[path] = data
    missing = [p for p in todo if p not in got]
    if missing:                                                    # second way: the zip of that commit (or of the branch if unknown)
        try:
            z = zipfile.ZipFile(io.BytesIO(_download_zip(commit or None)))
            names = z.namelist()
            top = names[0].split("/")[0] + "/" if names else ""
            for path in missing:
                if top + path in names:
                    data = z.read(top + path)
                    if ok(path, data):
                        got[path] = data
        except zipfile.BadZipFile:
            raise UpdateError("الملف اللي نزل من GitHub تالف. جرّب مرة ثانية.")
    return got, [p for p in todo if p not in got]


def apply(res=None):
    """Downloads the changed files, CHECKS each one against GitHub's fingerprint, writes only the ones that match."""
    res = res or check()
    todo = [p for p in sorted(set(res["changed"]) | set(res["new"])) if ".." not in p.split("/") and not p.startswith("/")]
    if not todo:
        return {"written": [], "failed": [], "pip": "", "needs_restart": False}
    got, failed = _fetch_files(todo, res)
    written = []
    for rel, data in got.items():
        dst = (ROOT / rel).resolve()
        if ROOT.resolve() not in dst.parents:
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        tmp = dst.with_name(dst.name + ".new")
        tmp.write_bytes(data)
        os.replace(tmp, dst)
        written.append(rel)
    pip = ""
    if "requirements.txt" in written:
        try:
            r = subprocess.run([sys.executable, "-m", "pip", "install", "-r", str(ROOT / "requirements.txt")], capture_output=True, text=True, timeout=600)
            pip = "ثُبّتت المكتبات الجديدة" if r.returncode == 0 else "تعذّر تثبيت مكتبات جديدة: " + (r.stderr or r.stdout)[-200:]
        except Exception as e:
            pip = f"تعذّر تثبيت مكتبات جديدة: {e}"
    return {"written": sorted(written), "failed": failed, "pip": pip,
            "needs_restart": any(w.endswith((".py", ".css", ".js")) for w in written)}


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
