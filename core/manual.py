"""Manual translation projects: extracted text, several drafts per file, a page plan (range / delete / insert / reorder),
paragraph styles and a full undo history. Everything is saved to disk after every change."""
import copy, re, shutil, time, uuid
from pathlib import Path
from threading import RLock
from . import parser, textcheck
from .config import DATA, read_json, write_json

ROOT = DATA / "manual"
ROOT.mkdir(exist_ok=True)
_lock = RLock()
MISSING = {"__missing__": True}
HIST_MAX = 300
HEAD_RE = re.compile(r"^(chapter|prologue|epilogue|interlude|afterword|foreword|preface|intro|introduction|part|volume|book)\b", re.I)


def _dir(pid):
    return ROOT / pid


def _ddir(pid):
    d = _dir(pid) / "drafts"
    d.mkdir(exist_ok=True)
    return d


def source_path(pid):
    return str(_dir(pid) / "source.pdf")


# ----------------------------------------------------------------------------- projects
def _chapters(path, units, pages):
    import fitz
    out = []
    try:
        for lvl, title, pg in fitz.open(path).get_toc():
            if 1 <= pg <= pages and str(title).strip():
                out.append({"title": str(title).strip()[:80], "page": pg - 1})
    except Exception:
        pass
    if not out:
        for u in units:
            t = u["text"].strip()
            if u.get("heading") and len(t) < 80 and HEAD_RE.match(t):
                out.append({"title": t, "page": u["page"]})
    seen, res = set(), []
    for c in out:
        k = (c["title"], c["page"])
        if k not in seen:
            seen.add(k)
            res.append(c)
    return res[:400]


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
            "created": int(time.time()), "extract_seconds": round(time.time() - t0, 1),
            "chapters": _chapters(str(d / "source.pdf"), units, info["pages"]), "last_draft": ""}
    write_json(d / "meta.json", meta)
    ensure_draft(pid)
    return pid


def load(pid):
    d = _dir(pid)
    return read_json(d / "meta.json", None), read_json(d / "units.json", [])


def save_meta(pid, meta):
    write_json(_dir(pid) / "meta.json", meta)


def list_projects():
    out = []
    for d in sorted(ROOT.iterdir(), key=lambda x: x.stat().st_mtime, reverse=True):
        m = read_json(d / "meta.json", None)
        if m:
            ds = list_drafts(m["id"])
            m["drafts"] = len(ds)
            out.append(m)
    return out


def list_all():
    """Every file the person worked on: manual projects first, then finished automatic translations not opened here yet.
    Returns [(label, value)] where value is "p:<id>" (manual project) or "j:<id>" (automatic job)."""
    from . import jobs
    out, taken = [], set()
    for m in list_projects():
        taken.add(m.get("from_job"))
        tag = "ترجمة آلية فُتحت للتعديل" if m.get("from_job") else "يدوي"
        out.append((f"{m['name']} · {m['pages']} صفحة · {tag}", "p:" + m["id"]))
    for m in jobs.list_jobs():
        if m.get("kind") == "pdf" and m.get("status") in ("ready", "partial") and m["id"] not in taken:
            out.append((f"{m['name']} · ترجمة آلية جاهزة (تُفتح للتعديل)", "j:" + m["id"]))
    return out


def delete(pid):
    shutil.rmtree(_dir(pid), ignore_errors=True)


def import_from_job(job_id):
    """Opens a file that was translated automatically, in the manual editor, with its translations as a draft."""
    from . import jobs
    meta, units = jobs.load(job_id)
    src = list((jobs._dir(job_id)).glob("source.pdf"))
    if not meta or not src:
        raise ValueError("هذا الملف ليس PDF أو لم يعد موجوداً")
    for p in list_projects():
        if p.get("from_job") == job_id:
            return p["id"], 0
    pid = create(str(src[0]))
    m, mu = load(pid)
    m["from_job"] = job_id
    m["name"] = meta.get("name") or m["name"]
    save_meta(pid, m)
    key = lambda u: (u["page"], tuple(round(v) for v in u["bbox"]))
    done = {key(u): u["tr"] for u in units if u.get("kind") == "text" and u.get("tr") and u.get("bbox")}
    did = ensure_draft(pid)
    d = load_draft(pid, did)
    n = 0
    for u in mu:
        t = done.get(key(u))
        if t:
            d["tr"][u["id"]] = t
            n += 1
    d["name"] = "من الترجمة الآلية"
    save_draft(pid, d)
    return pid, n


# ----------------------------------------------------------------------------- drafts
def new_draft_dict(name, pages):
    now = int(time.time())
    return {"id": uuid.uuid4().hex[:6], "name": name, "created": now, "updated": now, "page": 0, "grp": 0,
            "tr": {}, "src": {}, "ustyle": {}, "pstyle": {}, "deleted": {}, "extra": {},
            "plan": [{"k": "o", "p": i} for i in range(pages)],
            "range": {"on": False, "a": 1, "b": max(pages, 1), "outside": "keep"}, "ctx": "", "style": "", "hist": []}


def list_drafts(pid):
    out = []
    for f in sorted(_ddir(pid).glob("*.json"), key=lambda x: x.stat().st_ctime):
        d = read_json(f, None)
        if d:
            out.append({"id": d["id"], "name": d["name"], "updated": d.get("updated", 0)})
    return out


def load_draft(pid, did):
    return read_json(_ddir(pid) / f"{did}.json", None)


def save_draft(pid, d):
    d["updated"] = int(time.time())
    write_json(_ddir(pid) / f"{d['id']}.json", d)


def _migrate(pid):
    """Projects made by older versions kept translations inside units.json: move them into a draft."""
    meta, units = load(pid)
    old = {u["id"]: (u.get("manual") or u.get("tr")) for u in units if u.get("manual") or u.get("tr")}
    if not old:
        return
    d = new_draft_dict("مسودة 1", meta["pages"])
    d["tr"] = old
    save_draft(pid, d)
    for u in units:
        u.pop("manual", None)
        u.pop("tr", None)
    write_json(_dir(pid) / "units.json", units)


def ensure_draft(pid):
    with _lock:
        meta, _ = load(pid)
        if not list_drafts(pid):
            _migrate(pid)
        if not list_drafts(pid):
            save_draft(pid, new_draft_dict("مسودة 1", meta["pages"]))
        ds = [x["id"] for x in list_drafts(pid)]
        did = meta.get("last_draft") if meta.get("last_draft") in ds else ds[0]
        if meta.get("last_draft") != did:
            meta["last_draft"] = did
            save_meta(pid, meta)
        return did


def set_last_draft(pid, did):
    meta, _ = load(pid)
    meta["last_draft"] = did
    save_meta(pid, meta)


def create_draft(pid, name=None, copy_from=None):
    with _lock:
        meta, _ = load(pid)
        n = len(list_drafts(pid)) + 1
        if copy_from:
            d = copy.deepcopy(load_draft(pid, copy_from))
            d.update(id=uuid.uuid4().hex[:6], name=name or f"{d['name']} (نسخة)", created=int(time.time()), hist=[])
        else:
            d = new_draft_dict(name or f"مسودة {n}", meta["pages"])
        save_draft(pid, d)
        set_last_draft(pid, d["id"])
        return d["id"]


def rename_draft(pid, did, name):
    with _lock:
        d = load_draft(pid, did)
        d["name"] = name.strip() or d["name"]
        save_draft(pid, d)


def delete_draft(pid, did):
    with _lock:
        f = _ddir(pid) / f"{did}.json"
        if f.exists():
            f.unlink()
        ds = list_drafts(pid)
        if ds:
            set_last_draft(pid, ds[0]["id"])
        return ds[0]["id"] if ds else None


# ----------------------------------------------------------------------------- transactions + undo
def _get(d, path):
    cur = d
    for k in path:
        if isinstance(cur, dict) and k in cur:
            cur = cur[k]
        else:
            return MISSING
    return cur


def _put(d, path, value):
    cur = d
    for k in path[:-1]:
        cur = cur.setdefault(k, {})
    if value == MISSING:
        cur.pop(path[-1], None)
    else:
        cur[path[-1]] = copy.deepcopy(value)


class Tx:
    """Every change goes through here, so it can be undone with one click."""

    def __init__(self, d, label):
        self.d, self.label, self.inv = d, label, []

    def set(self, *path, value):
        old = _get(self.d, path)
        if old == value or (old == MISSING and value == MISSING):
            return self
        self.inv.append({"p": list(path), "o": copy.deepcopy(old)})
        _put(self.d, path, value)
        return self

    def commit(self):
        if self.inv:
            self.d["hist"].append({"label": self.label, "inv": self.inv[::-1], "t": int(time.time())})
            del self.d["hist"][:-HIST_MAX]
        return bool(self.inv)


def undo(d):
    if not d["hist"]:
        return None
    e = d["hist"].pop()
    for it in e["inv"]:
        _put(d, it["p"], it["o"])
    return e["label"]


def undo_option(d, *prefix):
    """Undoes the last change of ONE option only (e.g. ("ustyle", uid, "size")), leaving the other changes as they are."""
    prefix = list(prefix)
    for idx in range(len(d["hist"]) - 1, -1, -1):
        e = d["hist"][idx]
        mine = [it for it in e["inv"] if it["p"][:len(prefix)] == prefix]
        if mine:
            for it in mine:
                _put(d, it["p"], it["o"])
            e["inv"] = [it for it in e["inv"] if it not in mine]
            if not e["inv"]:
                d["hist"].pop(idx)
            return e["label"]
    return None


def page_uids(d, units, page):
    """Ids of every paragraph that belongs to one original page (the original ones and the ones you added)."""
    return {u["id"] for u in units if u["page"] == page} | {x for x, v in d["extra"].items() if v.get("page") == page}


def undo_page(d, units, page):
    """Undoes the last change that touched THIS page only. Changes to other pages made in the same step stay as they are."""
    uids = page_uids(d, units, page)

    def mine(it):
        p = it["p"]
        if len(p) < 2:
            return False
        if p[0] in ("tr", "src", "deleted", "ustyle"):
            return p[1] in uids
        if p[0] == "pstyle":
            return p[1] == str(page)
        if p[0] == "extra":
            pg = (d["extra"].get(p[1]) or {}).get("page")
            if pg is None and isinstance(it["o"], dict):
                pg = it["o"].get("page")
            return pg == page
        return False

    for idx in range(len(d["hist"]) - 1, -1, -1):
        e = d["hist"][idx]
        take = [it for it in e["inv"] if mine(it)]
        if take:
            for it in take:
                _put(d, it["p"], it["o"])
            e["inv"] = [it for it in e["inv"] if it not in take]
            if not e["inv"]:
                d["hist"].pop(idx)
            return e["label"]
    return None


def reset_page_to_original(d, units, page):
    """This page only: translations, edited source text, deleted flags, every style, the page style and the paragraphs you added,
    all back to the original file. One step that can be undone."""
    tx = Tx(d, "إعادة هذي الصفحة للأصل")
    for uid in sorted(page_uids(d, units, page)):
        for k in ("tr", "src", "deleted", "ustyle"):
            tx.set(k, uid, value=MISSING)
    for xid, x in list(d["extra"].items()):
        if x.get("page") == page:
            tx.set("extra", xid, value=MISSING)
    tx.set("pstyle", str(page), value=MISSING)
    return tx.commit()


def last_label(d):
    return d["hist"][-1]["label"] if d.get("hist") else ""


def reset_all(d):
    """Back to the very beginning (everything empty and default). One step that can be undone."""
    orig = max([e["p"] for e in d["plan"] if e["k"] == "o"] + [-1]) + 1
    fresh = new_draft_dict(d["name"], max(orig, 1))
    tx = Tx(d, "إعادة تعيين الكل")
    for k in ("tr", "src", "ustyle", "pstyle", "deleted", "extra", "plan", "range"):
        tx.set(k, value=fresh[k])
    return tx.commit()


# ----------------------------------------------------------------------------- the page plan
def effective_plan(d):
    """The pages of the output file in order. tr_on says whether the page is translated (inside the chosen range)."""
    r, out = d["range"], []
    for e in d["plan"]:
        e = dict(e)
        if e["k"] == "o":
            inside = (not r["on"]) or (r["a"] - 1 <= e["p"] <= r["b"] - 1)
            if not inside and r["outside"] == "delete":
                continue
            e["tr_on"] = inside
        else:
            e["tr_on"] = False
        out.append(e)
    return out


def _plan_edit(d, label, new_plan):
    return Tx(d, label).set("plan", value=new_plan).commit()


def plan_delete(d, eff_pos):
    entry = effective_plan(d)[eff_pos]
    plan = [e for e in d["plan"] if e != {k: v for k, v in entry.items() if k != "tr_on"}]
    return _plan_edit(d, "حذف صفحة", plan)


def _plan_index(d, entry):
    base = {k: v for k, v in entry.items() if k != "tr_on"}
    return d["plan"].index(base)


def plan_move(d, eff_from, eff_to):
    eff = effective_plan(d)
    if not (0 <= eff_from < len(eff)):
        return False
    plan = list(d["plan"])
    e = plan.pop(_plan_index(d, eff[eff_from]))
    eff_to = max(0, min(eff_to, len(eff) - 1))
    anchor = eff[eff_to] if eff_to != eff_from else None
    if anchor is None:
        return False
    idx = plan.index({k: v for k, v in anchor.items() if k != "tr_on"})
    plan.insert(idx + (1 if eff_to > eff_from else 0), e)
    return _plan_edit(d, "نقل صفحة", plan)


def plan_swap(d, a, b):
    eff = effective_plan(d)
    if a == b or not (0 <= a < len(eff) and 0 <= b < len(eff)):
        return False
    plan = list(d["plan"])
    ia, ib = _plan_index(d, eff[a]), _plan_index(d, eff[b])
    plan[ia], plan[ib] = plan[ib], plan[ia]
    return _plan_edit(d, "تبديل صفحتين", plan)


def plan_insert(d, eff_pos, entry, where="after", replace=False):
    """where: before / after the page at eff_pos. replace=True removes that page (the caller must have asked for confirmation)."""
    eff = effective_plan(d)
    plan = list(d["plan"])
    if not eff:
        plan.append(entry)
    else:
        i = _plan_index(d, eff[max(0, min(eff_pos, len(eff) - 1))])
        if replace:
            plan[i] = entry
        else:
            plan.insert(i + (1 if where == "after" else 0), entry)
    return _plan_edit(d, "استبدال صفحة" if replace else "إضافة صفحة", plan)


def import_page(pid, path, page_no=1, size=None):
    """Turns a page of another PDF, or an image, into a one-page PDF stored in the project, fitted INSIDE the size of the book's page
    (so it does not come out huge or tiny next to the other pages). Returns the plan entry."""
    import fitz
    ext = Path(path).suffix.lower()
    eid = uuid.uuid4().hex[:6]
    (_dir(pid) / "ext").mkdir(exist_ok=True)
    out = _dir(pid) / "ext" / f"{eid}.pdf"
    w, h = size or (595, 842)
    if ext == ".pdf":
        src = fitz.open(path)
        n = max(1, min(int(page_no or 1), len(src)))
        label = f"{Path(path).name} · صفحة {n}"
    elif ext in (".png", ".jpg", ".jpeg", ".webp", ".bmp"):
        src, n = None, 1
        label = Path(path).name
    else:
        raise ValueError("الصيغة غير مدعومة. استخدم PDF أو صورة (png, jpg, webp)")
    doc = fitz.open()
    page = doc.new_page(width=w, height=h)
    if src is not None:
        sw, sh = src[n - 1].rect.width, src[n - 1].rect.height
    else:
        from PIL import Image
        im = Image.open(path)
        sw, sh = im.size
    k = min(w / sw, h / sh)
    tw, th = sw * k, sh * k
    box = fitz.Rect((w - tw) / 2, (h - th) / 2, (w + tw) / 2, (h + th) / 2)
    if src is not None:
        page.show_pdf_page(box, src, n - 1)
    else:
        page.insert_image(box, filename=path)
    doc.save(str(out))
    return {"k": "e", "f": f"ext/{eid}.pdf", "label": label[:60]}


def page_size(pid, d, eff_pos):
    """The book's page size (the most common one among the original pages), so every imported page has exactly the same width and height."""
    import fitz
    from collections import Counter
    try:
        doc = fitz.open(source_path(pid))
        sizes = Counter((round(p.rect.width), round(p.rect.height)) for p in doc)
        if sizes:
            return tuple(float(x) for x in sizes.most_common(1)[0][0])
    except Exception:
        pass
    return None


# ----------------------------------------------------------------------------- paragraphs
def new_extra(d, units, orig_page, after_uid=""):
    """A paragraph that did not exist in the original: placed under the chosen paragraph, in the page's text column."""
    pu = [u for u in units if u["page"] == orig_page and u.get("translate")]
    longs = [u for u in pu if len(u["text"]) > 100] or pu
    x0 = min((u["bbox"][0] for u in longs), default=60)
    x1 = max((u["bbox"][2] for u in longs), default=500)
    anchor = next((u for u in pu if u["id"] == after_uid), None)
    size = sorted(u["size"] for u in longs)[len(longs) // 2] if longs else 11
    y = (anchor["bbox"][3] + 8) if anchor else (min((u["bbox"][1] for u in pu), default=60))
    xid = "X_" + uuid.uuid4().hex[:5]
    unit = {"id": xid, "kind": "text", "translate": True, "custom": True, "page": orig_page, "after": after_uid,
            "bbox": [x0, y, x1, y + size * 3], "text": "", "size": size, "bold": False, "color": 0, "align": "left"}
    tx = Tx(d, "إضافة فقرة")
    tx.set("extra", xid, value=unit)
    tx.commit()
    return xid


def delete_extra(d, xid):
    tx = Tx(d, "حذف فقرة مضافة")
    tx.set("extra", xid, value=MISSING)
    tx.set("tr", xid, value=MISSING)
    return tx.commit()


def toggle_deleted(d, uid):
    cur = d["deleted"].get(uid)
    tx = Tx(d, "استعادة فقرة" if cur else "حذف فقرة")
    tx.set("deleted", uid, value=MISSING if cur else True)
    return tx.commit(), (not cur)


def set_src(d, uid, text):
    """The text of a paragraph read from its picture (when the file's own text is unreadable)."""
    text = (text or "").strip()
    tx = Tx(d, "قراءة نص من الصورة")
    tx.set("src", uid, value=text if text else MISSING)
    return tx.commit()


def set_text(d, uid, text):
    text = (text or "").strip()
    tx = Tx(d, "تعديل نص")
    tx.set("tr", uid, value=text if text else MISSING)
    return tx.commit()


STYLE_KEYS = ("font", "size", "tcolor", "hl", "dx", "dy", "align")


def set_ustyle(d, uid, **kw):
    tx = Tx(d, "تنسيق فقرة")
    for k, v in kw.items():
        tx.set("ustyle", uid, k, value=MISSING if v in (None, "", 0, 0.0, False) else v)
    return tx.commit()


def reset_ustyle(d, uid, keys=STYLE_KEYS):
    tx = Tx(d, "إعادة تعيين تنسيق فقرة")
    for k in keys:
        tx.set("ustyle", uid, k, value=MISSING)
    return tx.commit()


PSTYLE_KEYS = ("font", "scale", "tcolor", "hl", "bg", "dx", "dy", "align")


def set_pstyle(d, page, **kw):
    tx = Tx(d, "تنسيق صفحة")
    for k, v in kw.items():
        tx.set("pstyle", str(page), k, value=MISSING if v in (None, "", False) else v)
    return tx.commit()


def set_box(d, page, idx, **kw):
    """Edits of one coloured box of the original page. kw: c (colour), dx, dy, dw, dh, del. Empty values are dropped;
    no values at all = the box goes back to the original."""
    val = {k: v for k, v in kw.items() if v not in (None, "", 0, 0.0, False)}
    return Tx(d, "تعديل صندوق ملوّن").set("pstyle", str(page), "boxes", str(idx), value=val if val else MISSING).commit()


def reset_page(d, page, units):
    """Page style + every paragraph style on the page + the background, back to default."""
    tx = Tx(d, "إعادة تعيين تنسيق الصفحة")
    tx.set("pstyle", str(page), value=MISSING)
    for u in units:
        if u["page"] == page:
            tx.set("ustyle", u["id"], value=MISSING)
    for xid, x in d["extra"].items():
        if x["page"] == page:
            tx.set("ustyle", xid, value=MISSING)
    return tx.commit()


def set_range(d, on, a, b, outside):
    return Tx(d, "نطاق الترجمة").set("range", value={"on": bool(on), "a": int(a or 1), "b": int(b or 1), "outside": outside or "keep"}).commit()


# ----------------------------------------------------------------------------- views for the editor and the builder
def page_items(units, d, orig_page):
    """The paragraphs of one original page (with the added ones in their place), merged with the draft."""
    items = []
    extras = [x for x in d["extra"].values() if x["page"] == orig_page]

    def view(u):
        st = d["ustyle"].get(u["id"], {})
        ps = d["pstyle"].get(str(orig_page), {})
        src = (d.get("src") or {}).get(u["id"])
        return {"uid": u["id"], "custom": bool(u.get("custom")), "en": src or u["text"], "has_src": bool(src),
                "garbled": (not src) and (not u.get("custom")) and textcheck.garbled(u["text"]), "bbox": u["bbox"],
                "ar": d["tr"].get(u["id"], ""),
                "deleted": bool(d["deleted"].get(u["id"])), "def_size": round(u["size"], 1),
                "def_color": "#%02x%02x%02x" % ((u.get("color", 0) >> 16) & 255, (u.get("color", 0) >> 8) & 255, u.get("color", 0) & 255),
                "font": st.get("font", ""), "size": st.get("size", 0), "tcolor": st.get("tcolor", ""), "hl": st.get("hl", ""),
                "dx": st.get("dx", 0), "dy": st.get("dy", 0), "align": st.get("align", ""), "page_font": ps.get("font", "")}

    for x in [e for e in extras if not e.get("after")]:
        items.append(view(x))
    for u in units:
        if u["page"] == orig_page and u.get("translate"):
            items.append(view(u))
            for x in [e for e in extras if e.get("after") == u["id"]]:
                items.append(view(x))
    return items


def merged_units(units, d):
    """All paragraphs with the draft applied: translation, style, removal flags. Ready for the builder."""
    out = []
    for u in list(units) + list(d["extra"].values()):
        if not u.get("translate"):
            continue
        c = dict(u)
        uid = u["id"]
        if d["deleted"].get(uid):
            c["remove"], c["tr"] = True, ""
        elif d["tr"].get(uid):
            c["tr"] = d["tr"][uid]
        us, ps = d["ustyle"].get(uid, {}), d["pstyle"].get(str(u["page"]), {})
        for src, dst in (("font", "font"),):
            v = us.get(src) or ps.get(src)
            if v:
                c[dst] = v
        if us.get("size"):
            c["size_abs"] = us["size"]
        elif ps.get("scale") and ps["scale"] != 100:
            c["size_scale"] = ps["scale"] / 100.0
        if us.get("tcolor") or ps.get("tcolor"):
            c["tcolor"] = us.get("tcolor") or ps.get("tcolor")
        if us.get("hl") or ps.get("hl"):
            c["hl"] = us.get("hl") or ps.get("hl")
        c["dx"] = float(us.get("dx", 0) or 0) + float(ps.get("dx", 0) or 0)     # the page's shift + the paragraph's own shift
        c["dy"] = float(us.get("dy", 0) or 0) + float(ps.get("dy", 0) or 0)
        if us.get("align") or ps.get("align"):
            c["align_ov"] = us.get("align") or ps.get("align")
        out.append(c)
    return out


def stats(units, d):
    tu = [u for u in units if u.get("translate")] + list(d["extra"].values())
    done = sum(1 for u in tu if d["tr"].get(u["id"]))
    return done, len(tu)
