import os, sys, tempfile
os.environ["SUB_DATA"] = tempfile.mkdtemp()
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import warnings; warnings.filterwarnings("ignore")
import gradio as gr
from core import keystore, priority, pool, manual, auth
auth.must_change = lambda: False
a = keystore.add_key("mock", "mock-a", label="جيميناي"); b = keystore.add_key("mock", "mock-b", label="غروك"); c = keystore.add_key("mock", "mock-c", label="أولاما")
ids = [k["id"] for k in keystore.load_keys()]
G, X, O = ids
priority.set_order("translate", [G, X, O]); priority.set_order("edit", [O, X])
msgs = [{"role": "user", "content": "[P_1] hi"}]
def who(role="translate"):
    m = {}; pool.call(msgs, role, meta=m); return m["name"]
assert who() == "جيميناي" and who("edit") == "أولاما"
keys = {k["id"]: k for k in keystore.load_keys()}
pool.POOL.cooldown(keys[G], 3600, "day", "limit"); assert who() == "غروك"
pool.POOL.cooldown(keys[X], 3600, "day", "limit"); assert who() == "أولاما"
pool.POOL.cooldown(keys[O], 3600, "day", "limit")
try:
    pool.call(msgs, "translate", meta={}, ) if False else None
    with pool.use_route(priority.new_route("translate", "auto", True, max_wait=1)): pool.call(msgs, "translate")
    raise SystemExit("should be busy")
except pool.AllBusy as e: print("busy ok:", str(e)[:60])
# manual editor: chosen key + fallback, review mode, notices
for k in keys.values(): pool.POOL.revive(k["id"])
from manual_ui import screen, h_files, h_text
from manual_ui.reg import C
with gr.Blocks() as demo: screen.build()
o = h_files.new_file("/tmp/sample.pdf"); v = lambda o, k: (lambda x: x.get("value") if isinstance(x, dict) else x)(o[C[k]])
pid, did = v(o, "pid"), v(o, "did")
r = h_text.ai_slot(pid, did, 0, 0, 1, X, True, "review", "auto", True); print("slot ->", list(r.values())[0][:30])
pool.POOL.cooldown(keys[X], 3600, "day", "limit")
rt = priority.new_route("translate", X, True); 
with pool.use_route(rt): m = {}; pool.call(msgs, "translate", meta=m)
assert m["name"] == "جيميناي", m          # chosen key exhausted -> priority order
r = h_text.ai_page(pid, did, 0, 0, True, "auto", True, "review", "auto", True)
r = h_text.review_slot(pid, did, 0, 0, 1, "auto", True, "review", "auto", True)
r = h_text.review_page(pid, did, 0, 0, "auto", True, "review", "auto", True)
# chat
from ui import tab_chat
h, _, tbl = tab_chat.send([], "مرحبا", "auto", True); assert h[-1]["role"] == "assistant" and "ثانية" in h[-1]["content"]; print(h[-1]["content"][-90:])
h, _, _ = tab_chat.send(h, "وش الحال", G, False); print(h[-1]["content"][-60:])
from ui import tab_settings
print(tab_settings.save_priority(G, X, "", "", "", O, "", "", "", ""), priority.get_order("translate"), priority.get_order("edit"))
print("OK")
