"""Saved conversations with the AIs (the chat tab): every chat is a small file, so you can come back to any of them."""
import re, shutil, time, uuid, base64, io, zipfile
from pathlib import Path
from .config import DATA, read_json, write_json

DIR = DATA / "chats"
DIR.mkdir(parents=True, exist_ok=True)
DOC_CHARS = 30000
IMG_EXT = (".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp")
DOC_EXT = (".pdf", ".txt", ".md", ".csv", ".json", ".docx")
NOTE_RE = re.compile(r"\s*<sub>.*?</sub>\s*$", re.S)


def _file(cid):
    return DIR / cid / "chat.json"


def new_id():
    return uuid.uuid4().hex[:8]


def load(cid):
    return read_json(_file(cid), None) if cid else None


def save(chat):
    chat["updated"] = time.time()
    (DIR / chat["id"]).mkdir(exist_ok=True)
    write_json(_file(chat["id"]), chat)


def create(model="auto"):
    return {"id": new_id(), "title": "محادثة جديدة", "created": time.time(), "updated": time.time(), "model": model, "msgs": []}


def list_chats():
    out = []
    for f in DIR.glob("*/chat.json"):
        c = read_json(f, None)
        if c:
            out.append(c)
    return sorted(out, key=lambda c: c.get("updated", 0), reverse=True)


def choices():
    return [(f"{c['title']} · {time.strftime('%d/%m %H:%M', time.localtime(c.get('updated', 0)))}", c["id"]) for c in list_chats()]


def delete(cid):
    shutil.rmtree(DIR / cid, ignore_errors=True)


def rename(cid, title):
    c = load(cid)
    if c and title.strip():
        c["title"] = title.strip()[:60]
        save(c)


def keep_file(cid, path):
    """Copies an uploaded file into the chat's own folder. -> {"path","name","kind"}"""
    p = Path(path)
    ext = p.suffix.lower()
    kind = "image" if ext in IMG_EXT else "doc" if ext in DOC_EXT else None
    if not kind:
        raise ValueError(f"الملف «{p.name}» غير مدعوم. المدعوم: صور ({'، '.join(e[1:] for e in IMG_EXT[:4])}) وملفات pdf وtxt وmd وcsv وjson وdocx")
    d = DIR / cid
    d.mkdir(exist_ok=True)
    dst = d / f"{uuid.uuid4().hex[:6]}_{p.name}"
    shutil.copy(p, dst)
    return {"path": str(dst), "name": p.name, "kind": kind}


def doc_text(path):
    ext = Path(path).suffix.lower()
    if ext == ".pdf":
        import fitz
        doc = fitz.open(path)
        txt = "\n".join(pg.get_text() for pg in doc)
    elif ext == ".docx":
        with zipfile.ZipFile(path) as z:
            xml = z.read("word/document.xml").decode("utf-8", "ignore")
        txt = re.sub(r"<[^>]+>", " ", xml.replace("</w:p>", "\n"))
    else:
        txt = Path(path).read_text(encoding="utf-8", errors="replace")
    txt = re.sub(r"[ \t]+", " ", txt).strip()
    return txt[:DOC_CHARS] + ("\n[... اقتُطع الباقي لطوله]" if len(txt) > DOC_CHARS else "")


def _data_uri(path):
    from PIL import Image
    im = Image.open(path).convert("RGB")
    im.thumbnail((1280, 1280))
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=85)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


def to_api(msgs, system, keep_images=6):
    """What the model receives: clean text (no notices), documents as text, only the latest pictures as pictures."""
    out = [{"role": "system", "content": system}]
    n = len(msgs)
    for i, m in enumerate(msgs):
        text = NOTE_RE.sub("", m.get("text", ""))
        docs = [f for f in m.get("files", []) if f["kind"] == "doc"]
        imgs = [f for f in m.get("files", []) if f["kind"] == "image"]
        for f in docs:
            text += f"\n\n[ملف مرفق: {f['name']}]\n{doc_text(f['path'])}"
        if imgs and m["role"] == "user" and i >= n - keep_images:
            out.append({"role": "user", "content": [{"type": "text", "text": text or "ما في هذي الصورة؟"}] +
                        [{"type": "image_url", "image_url": {"url": _data_uri(f["path"])}} for f in imgs]})
        else:
            out.append({"role": m["role"], "content": text + ("\n[أُرفقت صورة سابقاً]" if imgs else "")})
    return out


def to_display(msgs):
    """What the chat window shows: pictures as pictures, files as a line, the small notice under the answer."""
    out = []
    for m in msgs:
        for f in m.get("files", []):
            if f["kind"] == "image":
                out.append({"role": m["role"], "content": {"path": f["path"]}})
        text = m.get("text", "")
        docs = [f["name"] for f in m.get("files", []) if f["kind"] == "doc"]
        if docs:
            text = "📎 " + "، ".join(docs) + ("\n\n" + text if text else "")
        if m.get("note"):
            text += f"\n\n<sub>{m['note']}</sub>"
        if text.strip():
            out.append({"role": m["role"], "content": text})
    return out
