"""Reads the text of a picture WITHOUT any AI service: RapidOCR (offline, English/Chinese/Japanese kanji) and, when installed,
Tesseract (Arabic, Japanese, Korean ...). It only recognises letters: it never invents or "corrects" words."""
import io
import re
import shutil

_rapid = None
_rapid_failed = False


def _rapid_engine():
    global _rapid, _rapid_failed
    if _rapid is None and not _rapid_failed:
        try:
            from rapidocr_onnxruntime import RapidOCR
            _rapid = RapidOCR()
        except Exception:
            _rapid_failed = True
    return _rapid


def _tess_langs():
    exe = shutil.which("tesseract") or next((p for p in (r"C:\Program Files\Tesseract-OCR\tesseract.exe",
                                                          r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe") if shutil.os.path.exists(p)), None)
    if not exe:
        return None, []
    try:
        import pytesseract
        pytesseract.pytesseract.tesseract_cmd = exe
        have = set(pytesseract.get_languages(config=""))
    except Exception:
        return None, []
    return pytesseract, [l for l in ("eng", "ara", "jpn", "kor", "chi_sim", "chi_tra") if l in have]


def available():
    """What can read pictures here: a list like ["RapidOCR", "Tesseract"] (empty = nothing installed)."""
    out = []
    if _rapid_engine():
        out.append("RapidOCR")
    if _tess_langs()[0]:
        out.append("Tesseract")
    return out


_CJK = re.compile(r"[\u3040-\u30ff\u3400-\u9fff\uac00-\ud7af]")


def _join(lines):
    """Lines of ONE paragraph: joined with a space, but not between two CJK characters."""
    out = ""
    for ln in (l.strip() for l in lines if l and l.strip()):
        if out and not (_CJK.search(out[-1]) and _CJK.search(ln[0])):
            out += " "
        out += ln
    return out


def _by_rapid(png):
    eng = _rapid_engine()
    if not eng:
        return ""
    res, _ = eng(png)
    if not res:
        return ""
    res = sorted(res, key=lambda r: (round(min(p[1] for p in r[0]) / 8), min(p[0] for p in r[0])))
    return _join([r[1] for r in res])


def _by_tess(png, prefer=None):
    tess, langs = _tess_langs()
    if not tess or not langs:
        return ""
    from PIL import Image
    im = Image.open(io.BytesIO(png))
    lang = "+".join([l for l in (prefer or []) if l in langs] or langs)
    txt = tess.image_to_string(im, lang=lang, config="--psm 6")
    return _join(txt.splitlines())


def read_image(png_bytes):
    """Text of the picture, or "" when nothing was recognised. Raises RuntimeError when no engine is installed at all."""
    if not available():
        raise RuntimeError("لا يوجد قارئ نصوص محلي: نصّب RapidOCR (pip install rapidocr-onnxruntime) أو Tesseract.")
    text = _by_rapid(png_bytes)
    latin = sum(c.isascii() and c.isalpha() for c in text)
    if _tess_langs()[0] and (not text or latin < max(3, len(text) // 3)):      # not English: Arabic/Japanese/Korean need Tesseract
        t2 = _by_tess(png_bytes)
        if len(t2) > len(text) * 0.6:
            text = t2
    return text.strip()
