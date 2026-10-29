import os, sys, tempfile
tmp = tempfile.mkdtemp()
os.environ["SUB_DATA"] = tmp
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core import keystore, parser, translator, editor, glossary, builder

keystore.add_key("mock", "mock-key")
src = sys.argv[1]
kind, units, meta = parser.parse_any(src, tmp + "/img")
print("kind", kind, "meta", meta, "units", len(units), "translatable", sum(1 for u in units if u.get("translate")))
ctx = glossary.build_context(units, "en", "ar")
print("ctx", ctx[:80].replace("\n", " "))
left = translator.translate_all(units, "en", "ar", ctx, "", "")
print("untranslated left:", left)
print("edit patches:", len(editor.edit_pass(units, "en", "ar", ctx, "", "medium")))
print("find/replace:", editor.find_replace(units, "ترجمة تجريبية", "ترجمة"))
print("pdf:", builder.build_pdf(src, units, "ar", "/tmp/out_ar.pdf"))
print("epub:", builder.build_epub(units, "ar", "Test", "/tmp/out_ar.epub"))
import fitz
d = fitz.open("/tmp/out_ar.pdf")
for i in (0, 1):
    d[i].get_pixmap(dpi=70).save(f"/tmp/out_p{i+1}.png")
print("text sample:", d[0].get_text()[:120].replace("\n", " | "))
