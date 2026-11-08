"""Chat tab: formatting, saved conversations, uploads."""
import os, sys, tempfile
os.environ["SUB_DATA"] = tempfile.mkdtemp()
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from PIL import Image
from core import keystore, chats, llm, auth
auth.must_change = lambda: False
from ui import tab_chat

keystore.add_key("mock", "mock-ok1")

img = tempfile.mktemp(suffix=".png"); Image.new("RGB", (40, 40), "red").save(img)
txt = tempfile.mktemp(suffix=".txt"); open(txt, "w", encoding="utf-8").write("مرحبا من الملف")

cid, scr, _, _, _ = tab_chat.send(None, {"text": "هلا", "files": []}, "auto", True)
assert cid and chats.load(cid)["title"] == "هلا"
assert all(isinstance(m["content"], (str, dict)) for m in scr), scr
assert "<sub>" in scr[-1]["content"], "notice shown separately"
api = chats.to_api(chats.load(cid)["msgs"], "sys")
assert all("<sub>" not in m["content"] for m in api), "notice must not reach the model"

cid2, scr, _, _, _ = tab_chat.send(cid, {"text": "وش بالملف", "files": [txt, {"path": img}]}, "auto", True)
assert cid2 == cid and len(chats.load(cid)["msgs"]) == 4
assert any(isinstance(m["content"], dict) for m in scr), "image displayed"

# open an old chat after starting a new one
new_id, scr, *_ = tab_chat.new_chat()
assert new_id is None and scr == []
cid3, _, _, _, _ = tab_chat.send(None, {"text": "محادثة ثانية", "files": []}, "auto", True)
assert cid3 != cid and len(chats.list_chats()) == 2
back, scr, title = tab_chat.open_chat(cid)
assert back == cid and len(scr) >= 4

tab_chat.rename_chat(cid, "اسم جديد"); assert chats.load(cid)["title"] == "اسم جديد"
try:
    tab_chat.delete_chat(cid, False); assert False
except Exception: pass
tab_chat.delete_chat(cid, True); assert chats.load(cid) is None

# content blocks answer
class R: pass
assert chats.NOTE_RE.sub("", "نص\n\n<sub>x</sub>") == "نص"

# vision refused everywhere -> clear message, message not saved
for k in keystore.load_keys(): keystore.delete_key(k["id"])
keystore.add_key("mock", "mock-novision1")
try:
    tab_chat.send(None, {"text": "ما هذي", "files": [img]}, "auto", True); assert False
except Exception as e:
    assert "الصور" in str(e) or "Error" in type(e).__name__, e
assert len(chats.list_chats()) == 1, "failed message not saved"
print("chat OK")
