"""Build the final PDF (original pages kept, text replaced in place) and EPUB."""
import html, re
from pathlib import Path
from .config import FONTS

RTL = {"ar"}


def _rgb(c):
    return f"#{(c >> 16) & 255:02x}{(c >> 8) & 255:02x}{c & 255:02x}"


def _hex_rgb(h):
    h = (h or "#000000").lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    return tuple(int(h[k:k + 2], 16) / 255 for k in (0, 2, 4))


def _bg(page, rect):
    import fitz
    try:
        r = fitz.Rect(rect.x0 - 3, rect.y0 - 3, rect.x0 - 1, rect.y0 - 1) & page.rect
        if r.is_empty:
            r = fitz.Rect(rect.x0, rect.y0, rect.x0 + 2, rect.y0 + 2) & page.rect
        px = page.get_pixmap(clip=r, dpi=30)
        c = px.pixel(0, 0)
        return tuple(v / 255 for v in c[:3])
    except Exception:
        return (1, 1, 1)


# ------------------------------------------------------------------ fonts
DEFAULT_FAMILY = "Noto Naskh Arabic"
_fonts_cache = {}
_glyph_cache = {}


def _font(name):
    import fitz
    if name not in _fonts_cache:
        _fonts_cache[name] = fitz.Font(fontfile=str(FONTS / name))
    return _fonts_cache[name]


def _pretty(stem):
    return re.sub(r"(?<=[a-z])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])", " ", stem)


STYLE_AR = {
    "Noto Naskh Arabic": "نسخ", "Amiri": "نسخ كلاسيكي للكتب", "Amiri Quran": "نسخ مصحف", "Scheherazade New": "نسخ واضح للقراءة",
    "Lateef": "نسخ خفيف", "Harmattan": "نسخ حديث", "Noto Kufi Arabic": "كوفي", "Noto Sans Arabic": "حديث بسيط",
    "IBM Plex Sans Arabic": "حديث تقني", "Tajawal": "حديث عصري", "Almarai": "حديث مريح", "Zain": "حديث خفيف",
    "Aref Ruqaa": "رقعة", "Aref Ruqaa Ink": "رقعة بالحبر", "Noto Nastaliq Urdu": "نستعليق", "Mirza": "خط يدوي",
    "Katibeh": "خط كاتب يدوي", "Rakkas": "عناوين عريضة", "Lalezar": "عناوين سميكة", "Jomhuria": "عناوين ضيقة",
    "Vibes": "زخرفي", "Blaka": "زخرفي ثقيل", "Blaka Ink": "زخرفي بالحبر", "Blaka Hollow": "زخرفي مفرّغ",
}


def font_labels():
    """[(label shown in the lists, family name)] with the writing style in Arabic."""
    return [(f"{n} · {STYLE_AR[n]}" if n in STYLE_AR else n, n) for n in font_families()]


def font_families():
    """{display name: (regular file, bold file)} for every font in fonts/ that has Arabic letters."""
    fams = {}
    for f in sorted(FONTS.glob("*-Regular.ttf")):
        stem = f.name[:-len("-Regular.ttf")]
        try:
            if not _font(f.name).has_glyph(0x627):
                continue
        except Exception:
            continue
        bold = FONTS / f"{stem}-Bold.ttf"
        fams[_pretty(stem)] = (f.name, bold.name if bold.exists() else f.name)
    return fams


def list_fonts():
    return list(font_families())


def _has(font_name, ch):
    k = (font_name, ch)
    if k not in _glyph_cache:
        _glyph_cache[k] = bool(_font(font_name).has_glyph(ord(ch)))
    return _glyph_cache[k]


def _rich_text(text, font_name):
    """Escapes the text. Characters the Arabic font does not have (Latin letters, many symbols) go in a fallback-font span."""
    out, buf, fb = [], [], False

    def flush():
        if buf:
            t = html.escape("".join(buf))
            out.append(f"<span class='fb'>{t}</span>" if fb else t)
            buf.clear()

    for ch in text:
        if ch == "\n":
            flush()
            out.append("<br>")
            continue
        if ch.isspace():
            buf.append(ch)
            continue
        need = not _has(font_name, ch)
        if need != fb:
            flush()
            fb = need
        buf.append(ch)
    flush()
    return "".join(out)


def _font_css(tgt, font=None):
    """Kept for the automatic pipeline: one Arabic font for everything."""
    if tgt == "ar":
        fams = font_families()
        reg, bold = fams.get(font or DEFAULT_FAMILY) or fams.get(DEFAULT_FAMILY) or ("NotoNaskhArabic-Regular.ttf", "NotoNaskhArabic-Bold.ttf")
        return reg, bold
    return None, None


# ------------------------------------------------------------------ backgrounds
def _gradient_png(c1, c2, direction):
    import io
    from PIL import Image
    a, b = [tuple(int(v * 255) for v in _hex_rgb(c)) for c in (c1, c2)]
    n = 128
    img = Image.new("RGB", (n, n))
    px = img.load()
    for y in range(n):
        for x in range(n):
            t = {"vertical": y / (n - 1), "horizontal": x / (n - 1)}.get(direction, (x + y) / (2 * (n - 1)))
            px[x, y] = tuple(int(a[k] + (b[k] - a[k]) * t) for k in range(3))
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


def _draw_background(page, bg):
    if not bg or not bg.get("mode") or bg["mode"] == "none":
        return False
    if bg["mode"] == "solid":
        page.draw_rect(page.rect, color=None, fill=_hex_rgb(bg.get("c1")), overlay=False)
    else:
        page.insert_image(page.rect, stream=_gradient_png(bg.get("c1", "#ffffff"), bg.get("c2", "#cccccc"),
                                                          bg.get("dir", "vertical")), overlay=False, keep_proportion=False)
    return True


# ------------------------------------------------------------------ one page
def _fit(page, rect, body, css, arch, ymax):
    """Writes the text into the box; grows the box downwards a little before it ever shrinks the text."""
    h0 = rect.height
    last = rect
    for grow in (1.0, 1.15, 1.35):
        r = fitz_rect(rect.x0, rect.y0, rect.x1, max(rect.y1, min(ymax, rect.y0 + h0 * grow)))
        last = r
        spare, scale = page.insert_htmlbox(r, body, css=css, archive=arch, scale_low=0.92)
        if spare >= 0:
            return r, spare, scale
    spare, scale = page.insert_htmlbox(last, body, css=css, archive=arch, scale_low=0.5)
    return last, spare, scale


def fitz_rect(*a):
    import fitz
    return fitz.Rect(*a)


def _apply_page(doc, pno, us, obstacles, tgt, default_family=None, bg=None):
    """Replaces the original text of the given paragraphs on one page. Returns how many were shrunk to fit."""
    import fitz
    rtl = tgt in RTL
    page = doc[pno]
    W = page.rect.width
    shrunk = 0
    arch = fitz.Archive(str(FONTS)) if FONTS.exists() else None
    has_bg = _draw_background(page, bg)
    fams = font_families() if tgt == "ar" else {}
    dflt = fams.get(default_family or DEFAULT_FAMILY) or fams.get(DEFAULT_FAMILY) or ("NotoNaskhArabic-Regular.ttf", "NotoNaskhArabic-Bold.ttf")
    for u in us:
        if u.get("custom"):                   # an added paragraph has no original text to erase
            continue
        r = fitz.Rect(u["bbox"])
        page.add_redact_annot(r, fill=False if has_bg else _bg(page, r))
    try:
        page.apply_redactions(images=fitz.PDF_REDACT_IMAGE_NONE, graphics=fitz.PDF_REDACT_LINE_ART_NONE)
    except Exception:
        page.apply_redactions(images=fitz.PDF_REDACT_IMAGE_NONE)
    # the text column of the page (used to put short continuation lines back at the margin)
    longs = [v for v in obstacles if v.get("text") and len(v["text"]) > 100 and v.get("bbox")]
    col = (min(v["bbox"][0] for v in longs), max(v["bbox"][2] for v in longs)) if longs else None
    scratch = None
    for u in us:
        if u.get("remove") or not u.get("tr"):    # removed paragraphs are only erased, never rewritten
            continue
        x0, y0, x1, y1 = u["bbox"]
        h0 = y1 - y0
        size0 = u["size"]
        limit = page.rect.y1 - 24            # free space below this block (down to the next block)
        for v in obstacles:
            if v is not u and v["bbox"][1] >= y1 - 1 and v["bbox"][0] < x1 and v["bbox"][2] > x0:
                limit = min(limit, v["bbox"][1] - 3)
        ymax = max(limit, y0 + h0 * 1.35)
        if (col and h0 < size0 * 2.4 and (x1 - x0) < 0.6 * (col[1] - col[0]) and abs(x0 - col[0]) < 0.2 * (col[1] - col[0])
                and u.get("align", "left") == "left"):
            x0, x1 = col                      # a short line that starts at the margin: use the whole column
        if rtl and u.get("align") != "center":
            x0, x1 = W - x1, W - x0                      # mirror for right-to-left reading
        dx, dy = float(u.get("dx") or 0), float(u.get("dy") or 0)
        rect = fitz.Rect(x0 + dx, y0 + dy, x1 + dx, max(y1, min(limit, ymax)) + dy)
        ymax += dy
        a = u.get("align", "left")
        align = {"left": "right", "right": "left", "center": "center"}[a] if rtl else a
        if u.get("align_ov") in ("right", "left", "center", "justify"):      # an alignment you chose yourself
            align = u["align_ov"]
        if u.get("size_abs"):
            size = float(u["size_abs"])
        else:
            size = size0 * (1.04 if rtl else 1.0) * float(u.get("size_scale", 1.0))
        color = u.get("tcolor") or _rgb(u.get("color", 0))
        fam = fams.get(u.get("font")) or dflt if tgt == "ar" else None
        weight = "bold" if u.get("bold") else "normal"
        if tgt == "ar":
            reg, bold = fam
            faces = (f"@font-face{{font-family:'AR';src:url('{reg}');}}@font-face{{font-family:'AR';font-weight:bold;src:url('{bold}');}}"
                     "@font-face{font-family:'LAT';src:url('NotoSans-Regular.ttf');}"
                     "@font-face{font-family:'LAT';font-weight:bold;src:url('NotoSans-Bold.ttf');}.fb{font-family:'LAT';}")
            family = "'AR'"
            body = "<p style='margin:0'>" + _rich_text(u["tr"], reg) + "</p>"
        else:
            faces, family = "", "sans-serif"
            body = "<p style='margin:0'>" + html.escape(u["tr"]).replace("\n", "<br>") + "</p>"
        css = (faces + f"body{{font-family:{family};font-size:{size}pt;color:{color};text-align:{align};"
               f"direction:{'rtl' if rtl else 'ltr'};margin:0;font-weight:{weight};line-height:1.3;}}")
        if u.get("hl"):                       # a coloured box around the text: measure the real text height first
            if scratch is None:
                scratch = fitz.open()
                scratch.new_page(width=page.rect.width, height=page.rect.height)
            sp, _ = _fit(scratch[0], rect, body, css, arch, ymax)[1:]
            used = fitz.Rect(rect.x0, rect.y0, rect.x1, rect.y0 + max(size * 1.3, _fit_height(rect, sp)))
            scratch[0].clean_contents()
            pad = 2.5
            page.draw_rect(fitz.Rect(used.x0 - pad, used.y0 - pad, used.x1 + pad, used.y1 + pad), color=None,
                           fill=_hex_rgb(u["hl"]), overlay=True)
        r_used, spare, scale = _fit(page, rect, body, css, arch, ymax)
        if scale and scale < 1:
            shrunk += 1
    if scratch is not None:
        scratch.close()
    return shrunk


def _fit_height(rect, spare):
    return max(0.0, rect.height - max(spare, 0))


def _units_by_page(units):
    by_page, all_on_page = {}, {}
    for u in units:
        if u.get("bbox"):
            all_on_page.setdefault(u["page"], []).append(u)
        if u["kind"] == "text" and u.get("translate") and (u.get("tr") or u.get("remove")):
            by_page.setdefault(u["page"], []).append(u)
    return by_page, all_on_page


def build_pdf(src_pdf, units, tgt, out_path, font=None, page_styles=None):
    import fitz
    doc = fitz.open(src_pdf)
    by_page, all_on_page = _units_by_page(units)
    bgs = {int(p): (st or {}).get("bg") for p, st in (page_styles or {}).items() if (st or {}).get("bg")}
    shrunk = 0
    for pno in sorted(set(by_page) | set(bgs)):
        shrunk += _apply_page(doc, pno, by_page.get(pno, []), all_on_page.get(pno, []), tgt, font, bgs.get(pno))
    doc.subset_fonts()
    doc.save(out_path, garbage=3, deflate=True)
    doc.close()
    return {"pages": len(by_page), "shrunk_blocks": shrunk}


def crop_png(src_pdf, pno, bbox, dpi=200, margin=4):
    import fitz
    doc = fitz.open(src_pdf)
    page = doc[pno]
    r = fitz.Rect(bbox[0] - margin, bbox[1] - margin, bbox[2] + margin, bbox[3] + margin) & page.rect
    data = page.get_pixmap(clip=r, dpi=dpi).tobytes("png")
    doc.close()
    return data


def render_original(src_pdf, pno, boxes, out_png, dpi=90):
    """The ORIGINAL page as a picture, with a numbered red box around every paragraph (numbers match the editor)."""
    import fitz
    doc = fitz.open(src_pdf)
    page = doc[pno]
    for n, bb in boxes:
        r = fitz.Rect(bb)
        page.draw_rect(r, color=(0.85, 0, 0), width=0.8)
        top = r.y0 - 9 if r.y0 > 10 else r.y0
        page.draw_rect(fitz.Rect(r.x0, top, r.x0 + 8 + 4.2 * len(str(n)), top + 9), color=None, fill=(0.85, 0, 0))
        page.insert_text((r.x0 + 2, top + 7.5), str(n), fontsize=7.5, color=(1, 1, 1))
    page.get_pixmap(dpi=dpi).save(out_png)
    doc.close()


def build_plan_pdf(src_pdf, entries, units, tgt, out_path=None, font=None, page_styles=None, base_dir=None, only_pos=None, png=None, dpi=100):
    """Builds the output from the page plan: original pages, imported pages, blank pages, in the chosen order.
    only_pos: build just that one page (fast preview), and write a PNG instead of a PDF when png is given."""
    import fitz
    from pathlib import Path as _P
    src, out = fitz.open(src_pdf), fitz.open()
    by_page, all_on_page = _units_by_page(units)
    todo, last_size = [], (595, 842)
    positions = [only_pos] if only_pos is not None else range(len(entries))
    for pos in positions:
        e = entries[pos]
        if e["k"] == "o":
            out.insert_pdf(src, from_page=e["p"], to_page=e["p"])
            last_size = (out[-1].rect.width, out[-1].rect.height)
            if e.get("tr_on"):
                todo.append((len(out) - 1, e["p"]))
        elif e["k"] == "e":
            ex = fitz.open(str(_P(base_dir) / e["f"]))
            out.insert_pdf(ex, from_page=0, to_page=0)
            last_size = (out[-1].rect.width, out[-1].rect.height)
        else:
            out.new_page(width=last_size[0], height=last_size[1])
    shrunk = 0
    for idx, p in todo:
        bg = ((page_styles or {}).get(str(p)) or {}).get("bg")
        shrunk += _apply_page(out, idx, by_page.get(p, []), all_on_page.get(p, []), tgt, font, bg)
    info = {"pages": len(out), "shrunk_blocks": shrunk}
    if png:
        out[0].get_pixmap(dpi=dpi).save(png)
    else:
        out.subset_fonts()
        out.save(out_path, garbage=3, deflate=True)
    out.close()
    return info


def preview_page(src_pdf, units, tgt, pno, out_png, font=None, dpi=100, page_styles=None):
    """Renders ONE page exactly as it will look in the final file (fast: only this page is processed)."""
    import fitz
    doc = fitz.open(src_pdf)
    by_page, all_on_page = _units_by_page(units)
    bg = ((page_styles or {}).get(pno) or (page_styles or {}).get(str(pno)) or {}).get("bg")
    if pno in by_page or bg:
        _apply_page(doc, pno, by_page.get(pno, []), all_on_page.get(pno, []), tgt, font, bg)
    doc[pno].get_pixmap(dpi=dpi).save(out_png)
    doc.close()


EPUB_CSS_RTL = "body{direction:rtl;text-align:justify;line-height:1.9;font-family:serif;} h1,h2,h3{text-align:center;} img{max-width:100%;display:block;margin:1em auto;}"
EPUB_CSS_LTR = "body{line-height:1.6;font-family:serif;} h1,h2,h3{text-align:center;} img{max-width:100%;display:block;margin:1em auto;}"


def build_epub(units, tgt, title, out_path):
    from ebooklib import epub
    book = epub.EpubBook()
    book.set_title(title or "Translation")
    book.set_language(tgt)
    try:
        if tgt in RTL:
            book.set_direction("rtl")
    except Exception:
        pass
    css = epub.EpubItem(uid="css", file_name="style.css", media_type="text/css",
                        content=EPUB_CSS_RTL if tgt in RTL else EPUB_CSS_LTR)
    book.add_item(css)
    chapters, cur, ctitle, n_img, count = [], [], title or "", 0, 0

    def flush():
        nonlocal cur, ctitle, count
        if not cur:
            return
        count += 1
        ch = epub.EpubHtml(title=ctitle or f"{count}", file_name=f"ch{count}.xhtml", lang=tgt)
        ch.content = f"<html><body dir='{'rtl' if tgt in RTL else 'ltr'}'>" + "".join(cur) + "</body></html>"
        ch.add_item(css)
        book.add_item(ch)
        chapters.append(ch)
        cur, ctitle = [], ""

    for u in units:
        if u["kind"] == "image":
            try:
                data = Path(u["path"]).read_bytes()
                n_img += 1
                name = f"img{n_img}{Path(u['path']).suffix}"
                book.add_item(epub.EpubItem(uid=f"i{n_img}", file_name=name,
                                            media_type="image/" + Path(u["path"]).suffix[1:].replace("jpg", "jpeg"),
                                            content=data))
                cur.append(f"<img src='{name}' alt=''/>")
            except Exception:
                pass
            continue
        text = u.get("tr") or u["text"]
        if u.get("heading") and len(text) < 120:
            if len(cur) > 12:
                flush()
            if not ctitle:
                ctitle = text
            cur.append(f"<h2>{html.escape(text)}</h2>")
        else:
            cur.append(f"<p>{html.escape(text)}</p>")
        if len(cur) > 220:
            flush()
    flush()
    if not chapters:
        return False
    book.toc = tuple(chapters)
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    book.spine = ["nav"] + chapters
    epub.write_epub(out_path, book)
    return True


def build_txt(units, out_path):
    Path(out_path).write_text("\n\n".join((u.get("tr") or u.get("text", "")) for u in units if u["kind"] == "text"),
                              encoding="utf-8")
