import os, sys, tempfile, time
os.environ["SUB_DATA"] = tempfile.mkdtemp()
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core import keystore, jobs, quality
from core.pool import POOL
keystore.add_key("mock", "mock-bad-1"); keystore.add_key("mock", "mock-good-1")
for k in keystore.load_keys(): keystore.update_key(k["id"], label="سيئ" if "bad" in k["key"] else "جيد")
jid = jobs.create(sys.argv[1], "en", "ar", "", "", "medium")
for _ in range(150):
    m, u = jobs.load(jid)
    if m["status"] in ("ready", "error", "partial"): break
    time.sleep(0.3)
print("status:", m["status"])
r = quality.report(u)
print("report: total", r["total"], "| missing", r["missing"], "| flagged after retries", r["flagged"], "| by", r["by"])
assert m["status"] == "ready" and r["missing"] == 0
print("bad key quarantined:", bool(POOL.quarantine), "| events:", [e[2][:70] for e in POOL.events if "أوقفت" in e[2]][:1])
