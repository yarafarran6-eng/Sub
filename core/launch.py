"""Opening the site like an app: one clean window (no address bar) in Brave / Chrome / Edge, once the site is ready.
If the site is already running, the shortcut just opens the window and does not start a second copy."""
import os, socket, subprocess, threading, time, webbrowser
from pathlib import Path


def port_open(port, host="127.0.0.1"):
    try:
        with socket.create_connection((host, int(port)), timeout=0.6):
            return True
    except OSError:
        return False


def browser_exe():
    env = {k: os.environ.get(k, "") for k in ("ProgramFiles", "ProgramFiles(x86)", "LocalAppData")}
    rel = [r"BraveSoftware\Brave-Browser\Application\brave.exe", r"Google\Chrome\Application\chrome.exe", r"Microsoft\Edge\Application\msedge.exe"]
    for r in rel:                                    # Brave first, then Chrome, then Edge
        for base in env.values():
            f = Path(base).joinpath(*r.split("\\")) if base else None
            if f and f.exists():
                return str(f)
    return None


def open_site(url):
    exe = browser_exe()
    try:
        if exe:
            subprocess.Popen([exe, f"--app={url}"])
            return True
    except OSError:
        pass
    return webbrowser.open(url)


def open_when_ready(port, timeout=120):
    url = f"http://127.0.0.1:{port}"

    def run():
        end = time.time() + timeout
        while time.time() < end:
            if port_open(port):
                time.sleep(0.8)
                open_site(url)
                return
            time.sleep(0.5)
    threading.Thread(target=run, daemon=True).start()
