"""Chat tab: formatting, saved conversations, uploads."""
import os, sys, tempfile
os.environ["SUB_DATA"] = tempfile.mkdtemp()
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from PIL import Image
from core import keystore, chats, llm, auth
auth.must_change = lambda: False
from ui import tab_chat
os.environ["SUB_MOCK_SEARCH"] = "1"


def S(cid, mm, model, fb, priv=False, style="عادي", web=False, proj=""):
    return tab_chat.send(cid, mm, model, fb, priv, style, web, proj)

keystore.add_key("mock", "mock-ok1")

img = tempfile.mktemp(suffix=".png"); Image.new("RGB", (40, 40), "red").save(img)
txt = tempfile.mktemp(suffix=".txt"); open(txt, "w", encoding="utf-8").write("مرحبا من الملف")

cid, scr, _, _, _ = S(None, {"text": "هلا", "files": []}, "auto", True)
assert cid and chats.load(cid)["title"] == "هلا"
assert all(isinstance(m["content"], (str, dict)) for m in scr), scr
assert "<sub>" in scr[-1]["content"], "notice shown separately"
api = chats.to_api(chats.load(cid)["msgs"], "sys")
assert all("<sub>" not in m["content"] for m in api), "notice must not reach the model"

cid2, scr, _, _, _ = S(cid, {"text": "وش بالملف", "files": [txt, {"path": img}]}, "auto", True)
assert cid2 == cid and len(chats.load(cid)["msgs"]) == 4
assert any(isinstance(m["content"], dict) for m in scr), "image displayed"

# open an old chat after starting a new one (through the list menu commands)
new_id, scr, *_ = tab_chat.new_chat()
assert new_id is None and scr == []
cid3, _, _, _, html = S(None, {"text": "محادثة ثانية", "files": []}, "auto", True)
assert cid3 != cid and len(chats.list_chats()) == 2 and "محادثة ثانية" in html
back, scr, html, _p = tab_chat.act(cid3, f"open|{cid}")
assert back == cid and len(scr) >= 4
_, _, html, _p = tab_chat.act(cid, f"pin|{cid3}")
assert chats.list_chats()[0]["id"] == cid3 and "📌" in html          # pinned goes first
_, _, html, _p = tab_chat.act(cid, f"pin|{cid}")
assert sum(c.get("pinned", False) for c in chats.list_chats()) == 2   # more than one pinned
_, _, html, _p = tab_chat.act(cid, f"pin|{cid3}")
assert not chats.load(cid3).get("pinned")
tab_chat.act(cid, f"rename|{cid}|اسم | جديد"); assert chats.load(cid)["title"] == "اسم | جديد"
cur, scr, html, _p = tab_chat.act(cid, f"delete|{cid}")
assert chats.load(cid) is None and cur is None and scr == []

# content blocks answer
class R: pass
assert chats.NOTE_RE.sub("", "نص\n\n<sub>x</sub>") == "نص"

# vision refused everywhere -> clear message, message not saved
for k in keystore.load_keys(): keystore.delete_key(k["id"])
keystore.add_key("mock", "mock-novision1")
try:
    S(None, {"text": "ما هذي", "files": [img]}, "auto", True); assert False
except Exception as e:
    assert "الصور" in str(e) or "Error" in type(e).__name__, e
assert len(chats.list_chats()) == 1, "failed message not saved"
# image sent to a text-only model falls to a vision key; the follow-up "thanks" goes to the text-only key I picked
for k in keystore.load_keys(): keystore.delete_key(k["id"])
keystore.add_key("mock", "mock-novision2"); keystore.add_key("mock", "mock-vision1")
nv = [k["id"] for k in keystore.load_keys() if k["key"] == "mock-novision2"][0]
c, scr, *_ = S(None, {"text": "اقرأ", "files": [img]}, nv, True)
assert "رد تجريبي" in scr[-1]["content"]
c2, scr, *_ = S(c, {"text": "شكرا", "files": []}, nv, False)
assert "رد تجريبي" in scr[-1]["content"] and "novision" not in scr[-1]["content"].lower()

# ---- new features
for k in keystore.load_keys(): keystore.delete_key(k["id"])
keystore.add_key("mock", "mock-ok1"); keystore.add_key("mock", "mock-local1")
loc = [k["id"] for k in keystore.load_keys() if k["key"] == "mock-local1"][0]
c, scr, *_ = S(None, {"text": "وش آخر الأخبار", "files": []}, "auto", True, web=True)
assert "المصادر" in scr[-1]["content"] and "example.com/1" in scr[-1]["content"], scr[-1]
api = chats.to_api(chats.load(c)["msgs"], "s")
assert "نتائج بحث الويب" not in api[-2]["content"], "search block must not be saved"

try:                                                    # private with a non-local only chosen: refuses nothing external
    for k in list(keystore.load_keys()):
        if k["id"] == loc: keystore.update_key(k["id"], enabled=False)
    S(None, {"text": "سر", "files": []}, "auto", True, priv=True); assert False
except Exception as e:
    assert "محلي" in str(e), e
for k in keystore.load_keys(): keystore.update_key(k["id"], enabled=True)
from core import pool
before = len(pool.POOL.log_lines()) if hasattr(pool.POOL, "log_lines") else 0
c2, scr, *_ = S(None, {"text": "سر خاص", "files": []}, "auto", True, priv=True, web=True)
ch = chats.load(c2); assert ch["private"] and "خاصة" in ch["msgs"][-1]["note"] and "mock-local" not in ch["msgs"][-1]["note"]
assert "المصادر" not in scr[-1]["content"], "no web search in a private chat"
assert "🔒" in tab_chat.list_html(c2)

# regenerate, edit last, export, search, compare
scr, *_ = tab_chat.regenerate(c, "auto", True, False, "عادي", False, "")
assert len(chats.load(c)["msgs"]) == 2
scr, boxv, _h = tab_chat.edit_last(c); assert boxv["text"] == "وش آخر الأخبار" and chats.load(c)["msgs"] == []
f = tab_chat.export(c2); assert open(f["value"], encoding="utf-8").read().startswith("# ")
assert "سر خاص" in tab_chat.filter_list(None, "خاص") and "سر خاص" not in tab_chat.filter_list(None, "غير موجود")
ids = [k["id"] for k in keystore.load_keys()]
a, b = tab_chat.compare("سلام", ids[0], ids[1]); assert "رد تجريبي" in a and "رد تجريبي" in b

# novel context
from core import manual, chatctx
pid = manual.create("/tmp/sample.pdf")
ctxt = chatctx.project_context("p:" + pid, "Chapter")
assert "Chapter 1" in ctxt, ctxt[:300]
c3, scr, *_ = S(None, {"text": "وش العنوان", "files": []}, "auto", True, proj="p:" + pid)
assert "رد تجريبي" in scr[-1]["content"]
print("chat OK")
