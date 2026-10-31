"""Checks every translated paragraph before it is accepted, and builds the quality report."""
import re

_AR = re.compile(r"[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF\uFB50-\uFDFF\uFE70-\uFEFF]")
_LAT = re.compile(r"[A-Za-z]{2,}")
_LOW = re.compile(r"[a-z]{3,}")
_CJK = re.compile(r"[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff\uac00-\ud7af]")
_CYR = re.compile(r"[\u0400-\u04FF]")

# expected length of the translation compared with the source, by (source script, target language)
RATIO = {("latin", "ar"): (0.45, 2.0), ("cjk", "ar"): (0.9, 9.0), ("ar", "en"): (0.8, 2.8),
         ("latin", "en"): (0.5, 2.0), ("cjk", "en"): (1.0, 10.0), ("latin", "ja"): (0.12, 1.1), ("ar", "ja"): (0.1, 1.2)}


def kind_of(text):
    n = len(text) or 1
    if len(_CJK.findall(text)) / n > 0.2:
        return "cjk"
    if len(_AR.findall(text)) / n > 0.3:
        return "ar"
    return "latin"


def check(src, tr, tgt):
    """Returns a list of short Arabic problem descriptions (empty list = looks fine)."""
    tr = tr or ""
    if not tr.strip():
        return ["فقرة فارغة"]
    issues = []
    if "\ufffd" in tr:
        issues.append("رموز تالفة")
    if tgt in ("ar", "en") and _CJK.search(tr) and not _CJK.search(src):
        issues.append("حروف صينية أو يابانية أو كورية")
    if tgt in ("ar", "en", "ja") and _CYR.search(tr) and not _CYR.search(src):
        issues.append("حروف روسية")
    if tgt in ("en", "ja") and _AR.search(tr) and not _AR.search(src):
        issues.append("حروف عربية")
    if tgt == "ar" and (kind_of(src) != "latin" or _LOW.search(src)):
        words = _LAT.findall(tr)
        if words:
            issues.append("كلمات لاتينية متروكة: " + "، ".join(dict.fromkeys(words[:4])))
    if len(src.strip()) >= 40:
        lo, hi = RATIO.get((kind_of(src), tgt), (0.3, 3.5))
        r = len(tr.strip()) / len(src.strip())
        if r < lo:
            issues.append("الترجمة أقصر بكثير من الأصل (ربما تُرك جزء)")
        elif r > hi:
            issues.append("الترجمة أطول بكثير من المتوقع (ربما أُضيف كلام)")
    return issues


def report(units):
    tu = [u for u in units if u.get("translate")]
    done = [u for u in tu if u.get("tr")]
    flagged = [u for u in done if u.get("flag")]
    by, pages = {}, {}
    for u in done:
        b = by.setdefault(u.get("by") or "غير معروف", [0, 0])
        b[0] += 1
        b[1] += 1 if u.get("flag") else 0
    for u in tu:
        if not u.get("tr") or u.get("flag"):
            pages[u["page"] + 1] = pages.get(u["page"] + 1, 0) + 1
    src_c, tr_c = sum(len(u["text"]) for u in done), sum(len(u["tr"]) for u in done)
    return {"total": len(tu), "missing": len(tu) - len(done), "flagged": len(flagged),
            "ratio": (tr_c / src_c) if src_c else 0, "by": by,
            "bad_pages": sorted(pages.items(), key=lambda x: -x[1])[:15]}


def recheck(units, tgt):
    """Re-runs the checks on already translated paragraphs (so files translated by an older version get a real report)."""
    changed = 0
    for u in units:
        if u.get("translate") and u.get("tr"):
            fl = "؛ ".join(check(u["text"], u["tr"], tgt))
            if fl != (u.get("flag") or ""):
                if fl:
                    u["flag"] = fl
                else:
                    u.pop("flag", None)
                changed += 1
    return changed
