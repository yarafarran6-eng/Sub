import os, sys, tempfile, time
os.environ["SUB_DATA"] = tempfile.mkdtemp()
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core import keystore, jobs, quality
from core.keystore import PROVIDERS
from core.pool import POOL
PROVIDERS["mock"]["max_chars"] = 450                      # many small chunks so the bad key is judged on enough paragraphs
import fitz
d = fitz.open()
for i in range(10):
    pg = d.new_page(); y = 60
    for j in range(4):
        pg.insert_textbox(fitz.Rect(50, y, 540, y + 90), f"Alice walked slowly along the old road number {i}{j}, thinking about what her brother had said the night before.", fontsize=11); y += 100
d.save("/tmp/many.pdf")
keystore.add_key("mock", "mock-bad-1"); keystore.add_key("mock", "mock-good-1"); keystore.add_key("mock", "mock-good-2")
for k in keystore.load_keys(): keystore.update_key(k["id"], label="سيئ" if "bad" in k["key"] else "جيد " + k["key"][-1])
jid = jobs.create("/tmp/many.pdf", "en", "ar", "", "", "medium")
for _ in range(200):
    m, u = jobs.load(jid)
    if m["status"] in ("ready", "error", "partial"): break
    time.sleep(0.3)
r = quality.report(u)
print("status:", m["status"], "| missing", r["missing"], "| flagged", r["flagged"], "| by", r["by"])
print("bad key quarantined:", bool(POOL.quarantine))
print([e[2][:90] for e in POOL.events if "أوقفت" in e[2]][:1])
assert m["status"] == "ready" and r["missing"] == 0 and r["flagged"] == 0
print("states:", [s["state"][:60] for s in POOL.status()])
