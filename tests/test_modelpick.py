import json, os, sys, tempfile, threading
from http.server import BaseHTTPRequestHandler, HTTPServer
os.environ["SUB_DATA"] = tempfile.mkdtemp()
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core import keystore, modelpick

class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def _send(self, code, obj):
        b = json.dumps(obj).encode(); self.send_response(code); self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)
    def do_GET(self):
        if self.path.startswith("/a/v1/models"):
            return self._send(200, {"data": [{"id": "tiny-1b"}, {"id": "text-embedding-x"}, {"id": "big-70b-instruct"}, {"id": "other-8b"}]})
        self._send(404, {"error": {"message": "no models endpoint here"}})
    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        if self.path.startswith("/c/"):
            return self._send(401, {"error": {"message": "Invalid API Key"}})
        if self.path.startswith("/a/") and body.get("model") != "big-70b-instruct":
            return self._send(404, {"error": {"message": f"The model `{body.get('model')}` does not exist"}})
        if self.path.startswith("/b/") and body.get("model"):
            return self._send(400, {"error": {"message": "this gateway chooses the model itself"}})
        self._send(200, {"choices": [{"message": {"content": "OK"}, "finish_reason": "stop"}], "usage": {"prompt_tokens": 3, "completion_tokens": 1}})
srv = HTTPServer(("127.0.0.1", 8799), H); threading.Thread(target=srv.serve_forever, daemon=True).start()

A = keystore.add_key_generic("A", "k", "http://127.0.0.1:8799/a/v1", "")      # lists models, only one works
r = modelpick.auto_pick(A); print("A (picks from list)    ->", r["ok"], r["model"]); assert r["ok"] and r["model"] == "big-70b-instruct"
B = keystore.add_key_generic("B", "k", "http://127.0.0.1:8799/b/v1", "")      # no list, no model name needed
r = modelpick.auto_pick(B); print("B (no list, no model)  ->", r["ok"], repr(r["model"])); assert r["ok"] and r["model"] == ""
C = keystore.add_key_generic("C", "bad", "http://127.0.0.1:8799/c/v1", "")    # bad key
r = modelpick.auto_pick(C); print("C (bad key)            ->", r["ok"], r["kind"], "|", r["reason"][:80]); assert not r["ok"] and r["kind"] == "key"
D = keystore.add_key_generic("D", "k", "http://127.0.0.1:1/v1", "")           # nothing listening
r = modelpick.auto_pick(D); print("D (no server)          ->", r["ok"], r["kind"], "|", r["reason"][:70]); assert r["kind"] == "net"
print("ranking:", sorted(["tiny-1b", "llama-3.3-70b-versatile", "gpt-5", "gpt-4o-mini", "gemini-2.5-flash", "qwen-8b", "claude-opus-4"], key=modelpick.score, reverse=True))
