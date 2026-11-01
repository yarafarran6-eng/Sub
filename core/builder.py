"""Build the final PDF (original pages kept, text replaced in place) and EPUB."""
import html, re
from pathlib import Path
from .config import FONTS

RTL = {"ar"}


def _rgb(c):
    return f"#{(c >> 16) & 255:02x}{(c >> 8) & 255:02x}{c & 255:02x}"


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


def list_fonts():
    return sorted(f.name for f in FONTS.glob("*") if f.suffix.lower() in (".ttf", ".otf"))


def _font_css(tgt, font=None):
    faces = ""
    if font and (FONTS / font).exists():
        faces = f"@font-face{{font-family:'SubFont';src:url('{font}');}}@font-face{{font-family:'SubFont';font-weight:bold;src:url('{font}');}}"
        fam = "'SubFont'"
    elif tgt == "ar":
        faces = ("@font-face{font-family:'SubFont';src:url('NotoNaskhArabic-Regular.ttf');}"
                 "@font-face{font-family:'SubFont';font-weight:bold;src:url('NotoNaskhArabic-Bold.ttf');}")
        fam = "'SubFont'"
    elif tgt == "ja" and (FONTS / "NotoSansJP-Regular.ttf").exists():
        faces = "@font-face{font-family:'SubFont';src:url('NotoSansJP-Regular.ttf');}"
        fam = "'SubFont'"
    else:
        fam = "sans-serif"
    return faces, fam


def _apply_page(doc, pno, us, obstacles, tgt, faces, fam, arch):
    """Replaces the original text of the given paragraphs on one page. Returns how many were shrunk to fit."""
    import fitz
    rtl = tgt in RTL
    page = doc[pno]
    W = page.rect.width
    shrunk = 0
    for u in us:
        r = fitz.Rect(u["bbox"])
        page.add_redact_annot(r, fill=_bg(page, r))
    try:
        page.apply_redactions(images=fitz.PDF_REDACT_IMAGE_NONE, graphics=fitz.PDF_REDACT_LINE_ART_NONE)
    except Exception:
        page.apply_redactions(images=fitz.PDF_REDACT_IMAGE_NONE)
    for u in us:
        x0, y0, x1, y1 = u["bbox"]
        limit = page.rect.y1 - 24            # let the block grow downwards into free space before shrinking the text
        for v in obstacles:
            if v is not u and v["bbox"][1] >= y1 - 1 and v["bbox"][0] < x1 and v["bbox"][2] > x0:
                limit = min(limit, v["bbox"][1] - 3)
        y1 = max(y1, limit)
        if rtl and u.get("align") != "center":
            x0, x1 = W - x1, W - x0                      # mirror for right-to-left reading
        rect = fitz.Rect(x0, y0, x1, y1)
        a = u.get("align", "left")
        align = {"left": "right", "right": "left", "center": "center"}[a] if rtl else a
        size = u["size"] * (1.04 if rtl else 1.0)
        css = (faces + f"body{{font-family:{fam};font-size:{size}pt;color:{_rgb(u.get('color', 0))};"
               f"text-align:{align};direction:{'rtl' if rtl else 'ltr'};margin:0;"
               f"font-weight:{'bold' if u.get('bold') else 'normal'};line-height:1.35;}}")
        body = "<p style='margin:0'>" + html.escape(u["tr"]).replace("\n", "<br>") + "</p>"
        spare, scale = page.insert_htmlbox(rect, body, css=css, archive=arch, scale_low=0.5)
        if scale and scale < 1:
            shrunk += 1
    return shrunk


def _units_by_page(units):
    by_page, all_on_page = {}, {}
    for u in units:
        if u.get("bbox"):
            all_on_page.setdefault(u["page"], []).append(u)
        if u["kind"] == "text" and u.get("translate") and u.get("tr"):
            by_page.setdefault(u["page"], []).append(u)
    return by_page, all_on_page


def build_pdf(src_pdf, units, tgt, out_path, font=None):
    import fitz
    doc = fitz.open(src_pdf)
    faces, fam = _font_css(tgt, font)
    arch = fitz.Archive(str(FONTS)) if FONTS.exists() else None
    by_page, all_on_page = _units_by_page(units)
    shrunk = sum(_apply_page(doc, pno, us, all_on_page.get(pno, []), tgt, faces, fam, arch) for pno, us in by_page.items())
    doc.subset_fonts()
    doc.save(out_path, garbage=3, deflate=True)
    doc.close()
    return {"pages": len(by_page), "shrunk_blocks": shrunk}


def preview_page(src_pdf, units, tgt, pno, out_png, font=None, dpi=100):
    """Renders ONE page exactly as it will look in the final file (fast: only this page is processed)."""
    import fitz
    doc = fitz.open(src_pdf)
    faces, fam = _font_css(tgt, font)
    arch = fitz.Archive(str(FONTS)) if FONTS.exists() else None
    by_page, all_on_page = _units_by_page(units)
    if pno in by_page:
        _apply_page(doc, pno, by_page[pno], all_on_page.get(pno, []), tgt, faces, fam, arch)
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
