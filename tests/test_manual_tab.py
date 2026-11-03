import os, sys, tempfile, time
os.environ["SUB_DATA"] = tempfile.mkdtemp()
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import manual_tab as mt
from core import manual, keystore, jobs
keystore.add_key("mock", "mock-1")
mt._guard = lambda: None
val = lambda x: x.get("value") if isinstance(x, dict) else x
SL = lambda v, i, k: v[8 + i * 12 + k]            # slot i, component k (0 group,1 en,2 ar,3 delbtn,4 font,5 size,...)

v = mt.h_new("/tmp/sample.pdf")
pid, did = v[0], v[1]
assert len(v) == 224, len(v)
print("open ->", val(v[5])[:60], "| info:", val(v[6])[:70])
print("slot 0 visible:", SL(v, 0, 0)["visible"], "| first English:", val(SL(v, 0, 1))[:30], "| slots visible:", sum(1 for i in range(16) if SL(v, i, 0).get("visible")))

# autosave while typing + persistence
mt.h_blur(pid, did, 0, 0, "الفصل الأول", 0); mt.h_blur(pid, did, 0, 0, "مشت أليس ببطء.", 1)
d = manual.load_draft(pid, did); print("autosaved texts:", list(d["tr"].values()))
# per-paragraph style, then reset of ONE option only
mt.h_slot_style(pid, did, 0, 0, 1, "Amiri", 14, True, "#b00020", True, "#ffff00", 5, 0)
uid1 = manual.page_items(manual.load(pid)[1], manual.load_draft(pid, did), 0)[1]["uid"]
print("style saved:", manual.load_draft(pid, did)["ustyle"][uid1])
r = mt.h_slot_reset(pid, did, 0, 0, 1, "tcolor"); print("reset text colour only ->", [val(x) for x in r[:8]][:4], "| rest kept:", manual.load_draft(pid, did)["ustyle"][uid1])
mt.h_slot_reset(pid, did, 0, 0, 1, "all"); print("reset all of the paragraph ->", manual.load_draft(pid, did)["ustyle"].get(uid1))

# navigation, plan, range
v = mt.h_nav(pid, did, 0, 0, 1, "next"); print("next -> position", v[2] + 1)
v = mt.h_nav(pid, did, 1, 0, 3, "go"); print("go 3 -> position", v[2] + 1)
v = mt.h_req_del_page(pid, did, 2, 0); print("delete page asks:", val(v[-1])[:50], "| confirm visible:", v[-2]["visible"])
v = mt.h_yes(pid, did, 2, 0, v[-3]); print("after yes -> pages left:", len(v[8 + 192 + 14]), "|", val(v[5])[:50])
v = mt.h_undo(pid, did, 0, 0); print("undo ->", val(v[5]), "| pages:", len(v[8 + 192 + 14]))
v = mt.h_insert(pid, did, 0, 0, None, 1, "بعد الصفحة الحالية", True); print("blank page added after page 1 -> pages:", len(v[8 + 192 + 14]))
v = mt.h_insert(pid, did, 0, 0, "/tmp/pic.png", 1, mt.WHERE[2], False); print("replace asks confirmation:", v[-2]["visible"], "|", val(v[-1])[:60])
v = mt.h_no(pid, did, 0, 0); print("answer no -> still", len(v[8 + 192 + 14]), "pages")
v = mt.h_range(pid, did, 0, 0, True, 1, 2, "delete"); print("range 1..2, delete outside -> pages:", len(v[8 + 192 + 14]))
v = mt.h_range(pid, did, 0, 0, False, 1, 1, "keep"); print("range off -> pages:", len(v[8 + 192 + 14]))
v = mt.h_move(pid, did, 0, 0, 3); print("moved first page to 3 ->", [r[1] for r in v[8 + 192 + 14]][:4])
v = mt.h_swap(pid, did, 2, 0, 1); print("swap ->", [r[1] for r in v[8 + 192 + 14]][:4])
while manual.undo(d := manual.load_draft(pid, did)) is not None: manual.save_draft(pid, d)

# paragraphs: add / delete / restore
v = mt.h_add_para(pid, did, 0, 0, 1); print("added paragraph -> slots visible:", sum(1 for i in range(16) if SL(v, i, 0).get("visible")), "| custom label:", val(SL(v, 2, 1))[:28])
v = mt.h_slot_del(pid, did, 0, 0, 0); print("deleted paragraph 1 -> button:", val(SL(v, 0, 3)), "| ar interactive:", SL(v, 0, 2).get("interactive"))
v = mt.h_slot_del(pid, did, 0, 0, 0); print("restored -> button:", val(SL(v, 0, 3)))

# AI: one paragraph, then the whole page (keeps what I typed)
ar, msg = mt.h_ai_slot(pid, did, 0, 0, 3); print("AI one paragraph ->", val(ar)[:30], "|", msg[:40])
v = mt.h_ai_page(pid, did, 0, 0, True); print("AI page ->", val(v[5])[:50]); print("   typed text kept:", manual.load_draft(pid, did)["tr"].get(manual.page_items(manual.load(pid)[1], manual.load_draft(pid, did), 0)[1]["uid"]))

# page style + background preset + preview + final file
mt.h_page_style(pid, did, 0, "Tajawal", 110, True, "#222222", False, "#fff2a8", "none", "#ffffff", "#cccccc", "vertical")
r = mt.h_bg_preset(pid, did, 0, "تدرج: ذهبي"); print("background preset ->", [val(x) for x in r[:4]])
img, pos, info, m = mt.h_preview(pid, did, 0, 0, -1, "cur"); print("preview:", info[:60], "|", os.path.exists(img))
img, pos, info, m = mt.h_preview(pid, did, 0, 0, pos, "next"); print("preview next:", info[:40])
f, m = mt.h_build(pid, did, 0, 0); print("final file:", m[:90])
mt.h_page_reset(pid, did, 0, "bg"); print("background reset:", manual.load_draft(pid, did)["pstyle"]["0"].get("bg"))

# drafts: new, switch back, copy, delete with confirmation
v = mt.h_dnew(pid); did2 = v[1]; print("new draft is empty:", manual.load_draft(pid, did2)["tr"] == {}, "| old draft kept:", len(manual.load_draft(pid, did)["tr"]) > 0)
v = mt.h_dcopy(pid, did); print("copy has the text:", len(manual.load_draft(pid, v[1])["tr"]) == len(manual.load_draft(pid, did)["tr"]))
v = mt.h_dswitch(pid, did); print("switch back ->", val(v[5]))
v = mt.h_req_del_draft(pid, did2, 0, 0); v = mt.h_yes(pid, did, 0, 0, v[-3]); print("drafts after delete:", len(manual.list_drafts(pid)))
v = mt.h_req_reset(pid, did, 0, 0); v = mt.h_yes(pid, did, 0, 0, v[-3]); print("reset all -> texts:", len(manual.load_draft(pid, did)["tr"])); v = mt.h_undo(pid, did, 0, 0); print("undo the reset -> texts back:", len(manual.load_draft(pid, did)["tr"]) > 0)
# reopening later keeps everything
v = mt.h_open(pid); print("reopen ->", val(v[5])[:50])
# a file translated automatically can be opened here
jid = jobs.create("/tmp/sample.pdf", "en", "ar", "", "", "medium")
for _ in range(60):
    m_, _u = jobs.load(jid)
    if m_["status"] in ("ready", "partial", "error"): break
    time.sleep(0.3)
print("job choices:", mt._job_choices()[:1])
v = mt.h_from_job(jid); print("import from automatic job ->", val(v[5])[:80])
