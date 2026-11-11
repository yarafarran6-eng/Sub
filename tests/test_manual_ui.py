import os, sys, tempfile
os.environ["SUB_DATA"] = tempfile.mkdtemp()
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import warnings; warnings.filterwarnings("ignore")
import gradio as gr
from PIL import Image
from core import manual, keystore, auth
keystore.add_key("mock", "mock-1")
from manual_ui import screen, panel, h_files, h_text, h_pages, h_output
from manual_ui.reg import C
auth.must_change = lambda: False
with gr.Blocks() as demo:
    screen.build()
Image.new("RGB", (1200, 800), (10, 200, 10)).save("/tmp/mine.jpg")
v = lambda o, k: (lambda x: x.get("value") if isinstance(x, dict) else x)(o[C[k]])
o = h_files.new_file("/tmp/sample.pdf"); pid, did = v(o, "pid"), v(o, "did")
S = (pid, did, 0, 0)
assert o[C["s0_g"]]["visible"] and not o[C["s9_g"]]["visible"]
# autosave + per-paragraph style, step-back and reset of ONE option
h_text.blur(*S, "الفصل الأول", 0)
assert list(manual.load_draft(pid, did)["tr"].values()) == ["الفصل الأول"]
uid = manual.page_items(manual.load(pid)[1], manual.load_draft(pid, did), 0)[1]["uid"]
for kw in (dict(size=14), dict(size=16), dict(font="Amiri")):
    d = manual.load_draft(pid, did); manual.set_ustyle(d, uid, **kw); manual.save_draft(pid, d)
o = panel.stepback(*S, "para", 2, "size", "s1_"); assert manual.load_draft(pid, did)["ustyle"][uid] == {"size": 14, "font": "Amiri"}, manual.load_draft(pid, did)["ustyle"]
o = panel.reset(*S, "para", 2, "size", "s1_"); assert manual.load_draft(pid, did)["ustyle"][uid] == {"font": "Amiri"}
o = panel.apply(*S, "page", 1, "Tajawal", 110, "center", True, "#222222", False, "#fff2a8", 3, 0, "gradient", "#ffffff", "#000000", "vertical")
assert manual.load_draft(pid, did)["pstyle"]["0"]["scale"] == 110
panel.move(*S, "page", 1, "right", 5, "p_"); panel.preset(*S, "page", 1, "تدرج: ذهبي")
# page replace with MY image: must change + must fit the page + preview must show it at once
try: h_pages.insert(pid, did, "replace", 2, "/tmp/mine.jpg", 1, False, False); raise SystemExit("replace without confirmation must fail")
except gr.Error as e: print("no confirm ->", e.message[:40])
o = h_pages.insert(pid, did, "replace", 2, "/tmp/mine.jpg", 1, True, False)
d = manual.load_draft(pid, did); eff = manual.effective_plan(d)
assert eff[1]["k"] == "e" and len(eff) == 3 and v(o, "pg_prev") and os.path.exists(v(o, "pg_prev")), eff
import fitz
out = h_output.build(*S); pdf = fitz.open(v(out, "out"))
print("final page sizes:", [(round(p.rect.width), round(p.rect.height), len(p.get_images())) for p in pdf])
assert all(round(p.rect.width) == round(pdf[0].rect.width) for p in pdf) and len(pdf[1].get_images()) == 1
h_files.undo(*S)
assert manual.effective_plan(manual.load_draft(pid, did))[1]["k"] == "o"
# the same operations from the translation tab, on the OPEN page (cur is 0-based) - preview below the paragraphs must follow
n0 = len(manual.effective_plan(manual.load_draft(pid, did)))
try: h_pages.cur_ask_replace(pid, did, 1, None); raise SystemExit("asking to replace without a picture must fail")
except gr.Error: pass
pth, nm, pv = h_pages.cur_pick("/tmp/mine.jpg"); assert nm.endswith("mine.jpg") and pv["visible"] is True
q = h_pages.cur_ask_replace(pid, did, 1, pth); assert "الصفحة 2" in q[1] and "mine.jpg" in q[1]
o = h_pages.cur_replace(pid, did, 1, pth)
assert manual.effective_plan(manual.load_draft(pid, did))[1]["k"] == "e" and os.path.exists(h_text.pv_now(pid, did, v(o, "cur"))[0])
o = h_pages.cur_move(pid, did, 1, 3)
assert manual.effective_plan(manual.load_draft(pid, did))[2]["k"] == "e" and os.path.exists(h_text.pv_now(pid, did, v(o, "cur"))[0])
q = h_pages.cur_ask_delete(pid, did, 2); assert "الصفحة 3" in q[1]
o = h_pages.cur_delete(pid, did, 2)
assert len(manual.effective_plan(manual.load_draft(pid, did))) == n0 - 1 and os.path.exists(h_text.pv_now(pid, did, v(o, "cur"))[0])
h_files.undo(*S); h_files.undo(*S); h_files.undo(*S)
assert len(manual.effective_plan(manual.load_draft(pid, did))) == n0
# add before / blank / delete / move / swap / range
o = h_pages.insert(pid, did, "before", 1, None, 1, False, True); assert len(v(o, "plan")) == 4
h_pages.delete(pid, did, 1); h_pages.move(pid, did, 1, 3); h_pages.swap(pid, did, 1, 2)
o = h_pages.set_range(*S, True, 1, 2, "delete"); print("range ->", len(v(o, "plan")), "pages")
# drafts + files list (manual + auto)
o = h_files.new_draft(pid); d2 = v(o, "did"); assert d2 != did
o = h_files.switch_draft(pid, did); o = h_files.copy_draft(pid, did)
o = h_files.open_sel("p:" + pid); assert v(o, "pid") == pid
print("files:", [l for l, _ in manual.list_all()])
o = h_files.reset_all(pid, did); assert len(manual.effective_plan(manual.load_draft(pid, did))) == 3
# add / delete paragraph, AI with the mock key
o = h_text.add_para(*S, 1); o = h_text.slot_delete(*S, 0); o = h_text.slot_delete(*S, 0)
r = h_text.ai_slot(pid, did, 0, 0, 3, "auto", True, "only", "auto", True); print("AI ->", list(r.values())[0][:30])
o = h_text.ai_page(*S, True, "auto", True, "only", "auto", True)
png = h_output.preview(*S); assert os.path.exists(v(png, "pv_img"))
# username
print(auth.set_username("2222", "فيصل"), auth.check("faisal", "2222"), auth.check("فيصل", "2222"))
o = h_text.nav(*S, 0, "next"); assert v(o, "cur") == 1 and "2 من" in h_text.pv_now(pid, did, 1)[1], o
print("ALL OK")
