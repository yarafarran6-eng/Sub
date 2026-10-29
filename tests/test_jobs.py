import os, sys, tempfile, time
os.environ["SUB_DATA"] = tempfile.mkdtemp()
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core import auth, keystore, jobs

# auth: initial password works, must change, old one rejected after change
assert auth.check("x", "2222") and auth.must_change()
assert "غير صحيحة" in auth.change("bad", "newpass1")
assert "6" in auth.change("2222", "2222")
print(auth.change("2222", "newpass1"))
assert not auth.check("x", "2222") and auth.check("x", "newpass1") and not auth.must_change()

keystore.add_key("mock", "mock-1")
keystore.add_key("mock", "mock-2")
jid = jobs.create(sys.argv[1], "en", "ar", "literary", "", "medium")
for _ in range(60):
    m, _u = jobs.load(jid)
    if m["status"] in ("ready", "error", "partial"):
        break
    time.sleep(0.5)
print("status:", m["status"], m["stage"], m["pct"], m["msg"])
assert m["status"] == "ready"
m, u = jobs.load(jid)
assert all(x.get("tr") for x in u if x.get("translate"))
print("job ok, units:", len(u))
