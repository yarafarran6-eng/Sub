"""Single-password gate. Starts with the initial password and forces a change."""
import hashlib, hmac, os, time
from .config import DATA, read_json, write_json

FILE = DATA / "auth.json"
INITIAL_PASSWORD = "2222"
_fails = {"n": 0, "until": 0.0}
ENV_PW = os.getenv("SUB_PASSWORD", "")


def _hash(pw: str, salt: bytes) -> str:
    return hashlib.pbkdf2_hmac("sha256", pw.encode(), salt, 200_000).hex()


def _load():
    d = read_json(FILE, None)
    if not d:
        salt = os.urandom(16)
        d = {"salt": salt.hex(), "hash": _hash(INITIAL_PASSWORD, salt), "must_change": True}
        write_json(FILE, d)
    return d


def username() -> str:
    """The chosen user name ("" = any name is accepted, only the password decides)."""
    return "" if ENV_PW else (_load().get("username") or "")


def set_username(password: str, name: str) -> str:
    if ENV_PW:
        return "الاسم والكلمة مضبوطان من إعدادات الاستضافة، غيّرهما من هناك"
    d = _load()
    if not hmac.compare_digest(_hash(password or "", bytes.fromhex(d["salt"])), d["hash"]):
        return "كلمة السر الحالية غير صحيحة"
    name = (name or "").strip()
    if len(name) > 40:
        return "الاسم طويل، اجعله أقل من 40 حرفاً"
    d["username"] = name
    write_json(FILE, d)
    return f"تم تغيير اسم المستخدم إلى «{name}»" if name else "أُلغي اسم المستخدم: يكفي كلمة السر للدخول"


def check(username: str, password: str) -> bool:
    """Gradio auth callback. The password decides; the user name is checked only if one was chosen."""
    now = time.time()
    if now < _fails["until"]:
        return False
    if ENV_PW:
        ok = hmac.compare_digest((password or "").encode(), ENV_PW.encode())
    else:
        d = _load()
        ok = hmac.compare_digest(_hash(password or "", bytes.fromhex(d["salt"])), d["hash"])
        want = (d.get("username") or "").strip().lower()
        if ok and want and (username or "").strip().lower() != want:
            ok = False
    if ok:
        _fails["n"] = 0
    else:
        _fails["n"] += 1
        if _fails["n"] >= 5:
            _fails["until"] = now + 300
            _fails["n"] = 0
    return ok


def must_change() -> bool:
    if ENV_PW:
        return False
    return bool(_load().get("must_change"))


def change(old: str, new: str) -> str:
    if ENV_PW:
        return "كلمة السر مضبوطة من إعدادات الاستضافة (SUB_PASSWORD)، غيّرها من هناك"
    d = _load()
    if not hmac.compare_digest(_hash(old or "", bytes.fromhex(d["salt"])), d["hash"]):
        return "كلمة السر الحالية غير صحيحة"
    if len(new or "") < 6 or new == INITIAL_PASSWORD:
        return "كلمة السر الجديدة لازم تكون 6 خانات على الأقل ومختلفة عن الأولية"
    salt = os.urandom(16)
    write_json(FILE, {"salt": salt.hex(), "hash": _hash(new, salt), "must_change": False, "username": d.get("username", "")})
    return "تم تغيير كلمة السر"
