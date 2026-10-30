import os, sys, tempfile, time
os.environ["SUB_DATA"] = tempfile.mkdtemp()
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core import keystore, jobs, monitor
from core.pool import POOL
keystore.add_key("mock", "mock-limit-only")      # the ONLY key, and it keeps hitting its limit
jid = jobs.create(sys.argv[1], "en", "ar", "", "", "medium")
banner_seen = False
for _ in range(200):
    m, u = jobs.load(jid)
    if "كل المفاتيح وصلت حدها" in monitor.monitor_html(jid):
        banner_seen = True
    if m["status"] in ("ready", "error", "partial"):
        break
    time.sleep(0.3)
print("final:", m["status"], m["pct"], "| waiting banner shown:", banner_seen)
assert m["status"] == "ready", m
print("remaining untranslated:", sum(1 for x in u if x.get("translate") and not x.get("tr")))
for ts, lv, msg in list(POOL.events)[:4]:
    print("  ", lv, msg)
