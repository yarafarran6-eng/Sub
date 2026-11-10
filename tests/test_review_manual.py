"""The review tab works on the manual editor's drafts: load, edit, replace, export PDF / EPUB / TXT; changes are undoable."""
import os, sys, tempfile, io, contextlib
os.environ["SUB_DATA"] = tempfile.mkdtemp()
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import warnings; warnings.filterwarnings("ignore")
import gradio as gr
from core import manual, keystore, auth
keystore.add_key("mock", "mock-1")
auth.must_change = lambda: False
from manual_ui import screen, h_files
from manual_ui.reg import C
from ui import tab_review, review_manual as RM
with gr.Blocks():
    screen.build()
v = lambda o, k: (lambda x: x.get("value") if isinstance(x, dict) else x)(o[C[k]])
with contextlib.redirect_stdout(io.StringIO()):
    o = h_files.new_file("/tmp/sample.pdf")
pid, did = v(o, "pid"), v(o, "did")
meta, units = manual.load(pid)
tu = [u for u in units if u.get("translate")]
with manual._lock:
    d = manual.load_draft(pid, did)
    manual.set_text(d, tu[0]["id"], "مرحباً بكم في الرواية")
    manual.set_text(d, tu[1]["id"], "كان الجو بارداً جداً")
    manual.save_draft(pid, d)

ch = tab_review.review_choices()
sel = [v for _, v in ch if v.startswith("m|")][0]
assert sel == f"m|{pid}|{did}"
rows, ctx, info, _ = tab_review.load_review(sel)
assert any(r[3] == "مرحباً بكم في الرواية" for r in rows), rows[:2]
assert any(r[4] == "بدون ترجمة" for r in rows)
only, *_ = tab_review.load_review(sel, True)
assert all(r[4] for r in only)

rows[0][3] = "مرحباً بكم في الرواية الجديدة"
print(tab_review.save_review(sel, rows, "سياق جديد"))
d = manual.load_draft(pid, did)
assert d["tr"][rows[0][0]].endswith("الجديدة") and d["ctx"] == "سياق جديد"

new_rows, msg = tab_review.do_replace(sel, "بارداً", "حاراً")
assert "1" in msg and manual.load_draft(pid, did)["tr"][tu[1]["id"]] == "كان الجو حاراً جداً"
manual.undo(d := manual.load_draft(pid, did)); manual.save_draft(pid, d)            # the replace is one undo step
assert manual.load_draft(pid, did)["tr"][tu[1]["id"]] == "كان الجو بارداً جداً"

files, msg = tab_review.generate(sel, new_rows, "سياق جديد", True, True, True)
ext = sorted(os.path.splitext(f)[1] for f in files)
assert ext == [".epub", ".pdf", ".txt"], (ext, msg)
txt = open([f for f in files if f.endswith(".txt")][0], encoding="utf-8").read()
assert "مرحباً بكم" in txt
os.environ["SUB_EDITION"] = "lite"
try:
    tab_review.run_chat(sel, "اجعل الحوار حاداً", new_rows)
    raise SystemExit("AI command must be blocked in the light edition")
except gr.Error:
    pass
assert all(v.startswith("m|") for _, v in tab_review.review_choices())
print("review manual ok")
