"""Read PDF / EPUB / TXT into paragraph units with stable IDs (P_1, P_2, ...)."""
import re, statistics
from html.parser import HTMLParser
from pathlib import Path

END_PUNCT = tuple(".!?:;。！？」』”\"…")


def _has_letters(s):
    return bool(re.search(r"[^\W\d_]", s, re.UNICODE))


def parse_pdf(path, img_dir, on_page=None):
    import fitz
    img_dir = Path(img_dir)
    img_dir.mkdir(parents=True, exist_ok=True)
    doc = fitz.open(path)
    units, sizes, scanned = [], [], []
    for pno, page in enumerate(doc):
        if on_page:
            on_page(pno + 1, len(doc))
        W = page.rect.width
        d = page.get_text("dict")
        blocks = []
        n_text = 0
        for b in d["blocks"]:
            if b["type"] == 1:
                fn = img_dir / f"p{pno}_{len(blocks)}.{b.get('ext', 'png')}"
                try:
                    fn.write_bytes(b["image"])
                except Exception:
                    continue
                blocks.append({"kind": "image", "page": pno, "bbox": list(b["bbox"]), "path": str(fn)})
                continue
            lines, sz, bold, color = [], [], 0, 0
            for ln in b.get("lines", []):
                t = "".join(s["text"] for s in ln["spans"]).strip()
                if not t:
                    continue
                lines.append(t)
                for s in ln["spans"]:
                    if s["text"].strip():
                        sz.append(s["size"])
                        bold += 1 if s["flags"] & 16 else 0
                        color = s["color"]
            if not lines:
                continue
            text = ""
            for t in lines:
                if text.endswith("-") and t[:1].islower():
                    text = text[:-1] + t
                else:
                    text = (text + " " + t).strip()
            size = statistics.mean(sz)
            sizes.append(size)
            n_text += 1
            x0, y0, x1, y1 = b["bbox"]
            cx = (x0 + x1) / 2
            if abs(cx - W / 2) < W * 0.06 and (x1 - x0) < W * 0.8:
                align = "center"
            elif x0 > W * 0.55:
                align = "right"
            else:
                align = "left"
            blocks.append({"kind": "text", "page": pno, "bbox": [x0, y0, x1, y1], "text": text,
                           "size": round(size, 2), "bold": bold > len(sz) / 2, "color": color, "align": align})
        if n_text == 0 and any(x["kind"] == "image" for x in blocks):
            scanned.append(pno + 1)
        # merge consecutive blocks that are really one paragraph
        merged = []
        for b in blocks:
            p = merged[-1] if merged else None
            if (p and p["kind"] == "text" and b["kind"] == "text" and p["page"] == b["page"]
                    and abs(p["size"] - b["size"]) < 0.6 and abs(p["bbox"][0] - b["bbox"][0]) < 4
                    and 0 <= b["bbox"][1] - p["bbox"][3] < p["size"] * 0.7
                    and not p["text"].endswith(END_PUNCT) and p["align"] == b["align"]):
                p["text"] += " " + b["text"]
                p["bbox"] = [min(p["bbox"][0], b["bbox"][0]), p["bbox"][1],
                             max(p["bbox"][2], b["bbox"][2]), b["bbox"][3]]
            else:
                merged.append(b)
        units.extend(merged)
    body = statistics.median(sizes) if sizes else 11
    n = 0
    for u in units:
        n += 1
        u["id"] = f"P_{n}"
        if u["kind"] == "text":
            u["heading"] = bool(u["size"] >= body * 1.3 or (u["bold"] and len(u["text"]) < 90 and u["size"] >= body))
            u["translate"] = _has_letters(u["text"])
            u["tr"] = ""
        else:
            u["translate"] = False
    meta = {"pages": len(doc), "body_size": round(body, 2), "scanned_pages": scanned}
    doc.close()
    return units, meta


class _Html(HTMLParser):
    TAGS = {"p", "h1", "h2", "h3", "h4", "h5", "h6", "li", "blockquote"}

    def __init__(self):
        super().__init__()
        self.out, self.cur, self.tag, self.skip = [], [], None, 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self.skip += 1
        if tag in self.TAGS:
            self._flush()
            self.tag = tag

    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            self.skip = max(0, self.skip - 1)
        if tag in self.TAGS:
            self._flush()

    def handle_data(self, data):
        if not self.skip:
            self.cur.append(data)

    def _flush(self):
        t = re.sub(r"\s+", " ", "".join(self.cur)).strip()
        if t:
            self.out.append((self.tag or "p", t))
        self.cur = []


def parse_epub(path):
    from ebooklib import epub, ITEM_DOCUMENT
    book = epub.read_epub(path)
    units, n = [], 0
    for ci, item in enumerate(book.get_items_of_type(ITEM_DOCUMENT)):
        p = _Html()
        p.feed(item.get_content().decode("utf-8", "ignore"))
        p._flush()
        for tag, t in p.out:
            n += 1
            units.append({"id": f"P_{n}", "kind": "text", "page": ci, "text": t, "tr": "",
                          "heading": tag.startswith("h"), "translate": _has_letters(t), "size": 12})
    return units, {"pages": ci + 1 if units else 0, "scanned_pages": []}


def parse_txt(path):
    raw = Path(path).read_text(encoding="utf-8", errors="ignore")
    units = []
    for i, para in enumerate([x.strip() for x in re.split(r"\n\s*\n", raw) if x.strip()], 1):
        t = re.sub(r"\s*\n\s*", " ", para)
        units.append({"id": f"P_{i}", "kind": "text", "page": 0, "text": t, "tr": "",
                      "heading": len(t) < 60 and not t.endswith(END_PUNCT),
                      "translate": _has_letters(t), "size": 12})
    return units, {"pages": max(1, len(raw) // 2000), "scanned_pages": []}


def parse_any(path, img_dir, on_page=None):
    ext = Path(path).suffix.lower()
    if ext == ".pdf":
        return "pdf", *parse_pdf(path, img_dir, on_page)
    if ext == ".epub":
        return "epub", *parse_epub(path)
    return "txt", *parse_txt(path)
