"""Undo and reset for ONE page only: the other pages must stay exactly as they are."""
import os, sys, tempfile, warnings
os.environ["SUB_DATA"] = tempfile.mkdtemp()
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
warnings.filterwarnings("ignore")
import gradio as gr
from core import manual, auth
import app  # builds the screen so the handlers can answer
from manual_ui import h_files
auth.must_change = lambda: False

pid = manual.create("/tmp/sample.pdf"); did = manual.ensure_draft(pid)
meta, units = manual.load(pid)
by_page = {}
for u in units:
    if u.get("translate"): by_page.setdefault(u["page"], []).append(u["id"])
p0, p1 = by_page[0], by_page[1]

def edit(fn):
    d = manual.load_draft(pid, did); fn(d); manual.save_draft(pid, d)

edit(lambda d: manual.set_text(d, p0[0], "ترجمة صفحة 1"))
edit(lambda d: manual.set_text(d, p1[0], "ترجمة صفحة 2"))
edit(lambda d: manual.set_ustyle(d, p0[0], size=30))
edit(lambda d: manual.set_pstyle(d, 1, scale=120))
edit(lambda d: manual.set_text(d, p1[0], "ترجمة صفحة 2 معدلة"))          # LAST change overall belongs to page 2 (index 1)

# undo on page 1 (index 0): must undo ITS last change (the size), not the last change of the file
h_files.undo_page(pid, did, 0, 0)
d = manual.load_draft(pid, did)
assert "size" not in d["ustyle"].get(p0[0], {}), d["ustyle"]
assert d["tr"][p0[0]] == "ترجمة صفحة 1" and d["tr"][p1[0]] == "ترجمة صفحة 2 معدلة" and d["pstyle"]["1"]["scale"] == 120, "other page untouched"
h_files.undo_page(pid, did, 0, 0)                                           # next: its translation goes
assert manual.load_draft(pid, did)["tr"].get(p0[0], "") == ""
h_files.undo_page(pid, did, 0, 0)                                           # nothing left on this page: a message, no change
assert manual.load_draft(pid, did)["tr"][p1[0]] == "ترجمة صفحة 2 معدلة"

# reset page 2 (index 1) to the original: translations, style, added paragraph gone; page 1 untouched
edit(lambda d: manual.set_text(d, p0[0], "ما تتغير"))
edit(lambda d: manual.new_extra(d, units, 1, p1[0]))
q = h_files.ask_reset_page(pid, did, 1); assert "رقم 2" in q[1]
h_files.reset_page(pid, did, 1, 0)
d = manual.load_draft(pid, did)
assert not d["tr"].get(p1[0]) and "1" not in d["pstyle"] and not any(x["page"] == 1 for x in d["extra"].values()), d
assert d["tr"][p0[0]] == "ما تتغير", "page 1 keeps its translation"
h_files.undo(pid, did, 1, 0)                                                # one general undo brings the whole page back
d = manual.load_draft(pid, did)
assert d["tr"][p1[0]] == "ترجمة صفحة 2 معدلة" and d["pstyle"]["1"]["scale"] == 120
print("page undo OK")
