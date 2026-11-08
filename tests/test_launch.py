import os, sys, socket, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from pathlib import Path
from core import launch
s = socket.socket(); s.bind(("127.0.0.1", 0)); s.listen(1); port = s.getsockname()[1]
assert launch.port_open(port); s.close(); assert not launch.port_open(port)
tmp = Path(tempfile.mkdtemp()); exe = tmp / "BraveSoftware" / "Brave-Browser" / "Application" / "brave.exe"; exe.parent.mkdir(parents=True); exe.write_text("x")
(tmp / "Google" / "Chrome" / "Application").mkdir(parents=True); (tmp / "Google" / "Chrome" / "Application" / "chrome.exe").write_text("x")
os.environ["ProgramFiles"] = str(tmp)
assert launch.browser_exe() == str(exe), launch.browser_exe()                  # Brave first
exe.unlink(); assert launch.browser_exe().endswith("chrome.exe")
calls = []; launch.subprocess.Popen = lambda a, **k: calls.append(a)
launch.open_site("http://127.0.0.1:7860"); assert calls[0][1] == "--app=http://127.0.0.1:7860", calls
print("launch OK")
