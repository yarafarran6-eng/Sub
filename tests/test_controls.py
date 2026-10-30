import os, sys, tempfile, time
os.environ["SUB_DATA"] = tempfile.mkdtemp()
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core import keystore, jobs
from core.pool import POOL
keystore.add_key("mock", "mock-limit-only")          # slow on purpose (keeps hitting its limit)
jid = jobs.create(sys.argv[1], "en", "ar", "", "", "medium")
time.sleep(1.2)
print("resume while running  ->", jobs.enqueue(jid))
assert jobs.enqueue(jid) == "already_running"
jobs.cancel(jid)
print("resume right after stop->", jobs.enqueue(jid))
t0 = time.time()
for _ in range(240):
    m, u = jobs.load(jid)
    if m["status"] in ("ready", "error", "partial"): break
    time.sleep(0.3)
print("final:", m["status"], m["pct"], f"({time.time()-t0:.1f}s)")
assert m["status"] == "ready"
starts = [e for e in POOL.events if "بدأت معالجة" in e[2]]
print("times the job really started:", len(starts), "(expected 2: first run + restart after stop)")
# stop while queued behind another job, then resume
j2 = jobs.create(sys.argv[1], "en", "ar", "", "", "medium"); jobs.cancel(j2); time.sleep(3)
m2, _ = jobs.load(j2); print("stopped before start:", m2["status"])
print("then resume:", jobs.enqueue(j2))
for _ in range(240):
    m2, _ = jobs.load(j2)
    if m2["status"] in ("ready", "error", "partial"): break
    time.sleep(0.3)
print("second job final:", m2["status"]); assert m2["status"] == "ready"
