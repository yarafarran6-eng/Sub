"""Starts the app WITHOUT the login, on port 7990, for browser tests."""
import os, sys, tempfile, time
os.environ.setdefault("SUB_DATA", tempfile.mkdtemp())
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import app
from core import auth, keystore
auth.must_change = lambda: False
keystore.add_key("mock", "mock-1")
app.demo.queue().launch(server_port=7990, css=app.CSS, js=app.JS, theme=app.THEME, show_error=True, prevent_thread_lock=True)
time.sleep(int(os.getenv("SERVE_SECONDS", "600")))
