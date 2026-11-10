"""The light edition for a friend: no automatic-translation tab, no AI commands in the review tab; the rest is there."""
import json, os, subprocess, sys, tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CODE = r'''
import sys, warnings; warnings.filterwarnings("ignore")
sys.path.insert(0, %r)
import app, gradio as gr
tabs = {b.label: b.visible for b in app.demo.blocks.values() if isinstance(b, gr.Tab)}
btn = [b for b in app.demo.blocks.values() if isinstance(b, gr.Button) and b.value == "نفّذ"]
par = btn[0].parent
print(__import__("json").dumps({"tabs": tabs, "ai_cmd_visible": par.visible if par is not None else None}))
''' % str(ROOT)


def run(lite_file):
    data = Path(tempfile.mkdtemp())
    if lite_file:
        (data / "edition.txt").write_text("lite", encoding="utf-8")
    env = dict(os.environ, SUB_DATA=str(data))
    env.pop("SUB_EDITION", None)
    out = subprocess.run([sys.executable, "-c", CODE], capture_output=True, text=True, env=env, cwd=str(ROOT))
    assert out.returncode == 0, out.stderr[-600:]
    return json.loads(out.stdout.strip().splitlines()[-1])


full, lite = run(False), run(True)
auto = [k for k in full["tabs"] if "الترجمة الآلية" in k][0]
assert full["tabs"][auto] is True and full["ai_cmd_visible"] is True
assert lite["tabs"][auto] is False and lite["ai_cmd_visible"] is False
others = [k for k in lite["tabs"] if k != auto]
assert all(lite["tabs"][k] for k in others), lite["tabs"]          # keys, manual editor, review/export, chat, settings stay
assert any("المراجعة" in k for k in others) and any("المحرر" in k for k in others)
print("edition ok")
