import os, sys, tempfile, time
os.environ["SUB_DATA"] = tempfile.mkdtemp()
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core import keystore, jobs, monitor
from core.pool import POOL

# one dead key, one key that hits rate limits often, one healthy key
keystore.add_key("mock", "mock-dead-1")
keystore.add_key("mock", "mock-limit-1")
keystore.add_key("mock", "mock-ok-1")
jid = jobs.create(sys.argv[1], "en", "ar", "", "", "medium")
seen, last_pct = [], 0
for _ in range(120):
    m, u = jobs.load(jid)
    pct = m.get("pct", 0)
    assert pct >= last_pct - 0, f"progress went backwards {last_pct} -> {pct}"
    last_pct = pct
    seen.append(m["stage"])
    if m["status"] in ("ready", "error", "partial"):
        break
    time.sleep(0.4)
m, u = jobs.load(jid)
print("final:", m["status"], m["stage"], m["pct"], "|", m["live"].get("label"))
assert m["status"] == "ready", m
print("stages seen:", sorted(set(seen)))
print("events:")
for ts, lv, msg in list(POOL.events)[:8]:
    print("  ", lv, msg)
# resume must continue from existing progress, not restart
for x in u[:2]:
    if x.get("translate"): x["tr"] = ""
jobs.save_units(jid, u); jobs.set_state(jid, edited=True)
jobs.enqueue(jid)
time.sleep(0.3)
for _ in range(60):
    m, u2 = jobs.load(jid)
    if m["status"] in ("ready", "error", "partial"): break
    time.sleep(0.4)
print("after resume:", m["status"], m["pct"])
assert m["status"] == "ready"
html = monitor.monitor_html(jid); print("monitor html chars:", len(html), "| keys html chars:", len(monitor.keys_html()))
print("page stats:", jobs.page_stats(u2))
