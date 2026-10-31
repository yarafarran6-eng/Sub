import json, os, sys, tempfile, threading, time
from http.server import BaseHTTPRequestHandler, HTTPServer
os.environ["SUB_DATA"] = tempfile.mkdtemp()
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core import keystore, llm, modelpick
from core.pool import POOL, NoKeys, call

class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def _s(self, c, o, h=None):
        b = json.dumps(o).encode(); self.send_response(c); self.send_header("Content-Type", "application/json")
        for k, v in (h or {}).items(): self.send_header(k, v)
        self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)
    def do_GET(self): self._s(404, {"error": {"message": "no list"}})
    def do_POST(self):
        self.rfile.read(int(self.headers["Content-Length"]))
        if "/zero/" in self.path:
            return self._s(429, {"error": {"message": "You exceeded your current quota. Quota exceeded for metric: generate_content_free_tier_requests, limit: 0, model: gemini-x"}})
        if "/day/" in self.path:
            return self._s(429, {"error": {"message": "Rate limit reached on requests per day (RPD): Limit 50"}}, {"Retry-After": "70140"})
        self._s(200, {"choices": [{"message": {"content": "OK"}, "finish_reason": "stop"}], "usage": {"prompt_tokens": 3, "completion_tokens": 1}})
srv = HTTPServer(("127.0.0.1", 8797), H); threading.Thread(target=srv.serve_forever, daemon=True).start()
Z = keystore.add_key_generic("Z", "k", "http://127.0.0.1:8797/zero/v1", "m")
D = keystore.add_key_generic("D", "k", "http://127.0.0.1:8797/day/v1", "m")
for k in (Z, D):
    try: llm.chat(k, [{"role": "user", "content": "x"}])
    except llm.RateLimited as e: print(k["label"], "->", e.reason, f"wait={int(e.retry_after)}s", "|", e.detail[:70])
r = modelpick.auto_pick(Z); print("auto_pick on zero quota ->", r["ok"], r["kind"], "|", r["reason"][:90])
keystore.delete_key(D["id"])                       # only the zero-quota key left
try: call([{"role": "user", "content": "x"}], role="translate")
except NoKeys as e: print("NoKeys:", str(e)[:260])
print("events:"); [print("  ", e[2][:210]) for e in list(POOL.events)[:2]]
# a real daily wait: the status must show the service's own reply
keystore.add_key_generic("D2", "k", "http://127.0.0.1:8797/day/v1", "m")
import threading as T
T.Thread(target=lambda: call([{"role": "user", "content": "x"}], role="translate"), daemon=True).start()
time.sleep(2)
st = [s for s in POOL.status() if s["css"] == "wait"]
print("waiting state:", st[0]["state"][:200] if st else "none")
from core import monitor
print("banner has reason:", "رد الخدمة" in "".join(s["state"] for s in st))
