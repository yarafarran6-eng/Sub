"""Tab 5: chat with the AIs about anything. Pick one, switch any time; when its limit ends the next one in your priority answers."""
import html as _h
import time
import gradio as gr
from core import chats, llm, priority
from core.keystore import load_keys
from core.pool import AllBusy, NoKeys, POOL, call, kname, use_route
from .common import guard, safe

SYSTEM = ("You are a helpful assistant inside a translation app. Always reply in the same language as the user's last message. "
          "If the user writes Arabic, reply in simple, clear Arabic (plain words, no unneeded English, never Chinese or any other language unless the user asks). "
          "Format with simple Markdown: short paragraphs, bullet lists when listing, code only inside code blocks. "
          "Do not add signatures or notes about yourself. If you cannot do something (for example create images, video or audio), say so briefly and suggest what you can do instead.")


def remaining_html():
    """A small table: every AI and what is left of its limit now."""
    rows = []
    now = time.time()
    for s in POOL.status():
        k = s["k"]
        r = POOL._rt(k["id"])
        if not k.get("enabled"):
            continue
        st = "ينتظر تجدد الحد" if r["cool"] > now else ("مرفوض" if r["dead"] else "جاهز")
        rows.append(f"<tr><td><b>{kname(k)}</b><div class='sub'>{k.get('model') or 'تلقائي'}</div></td><td>{st}</td><td>{priority.brief_limit(k)}</td></tr>")
    if not rows:
        return "<div class='empty'>ما أضفت أي مفتاح بعد. أضف من تبويب المفاتيح.</div>"
    return "<div class='tbl'><table><thead><tr><th>الذكاء</th><th>الحالة</th><th>المتبقي</th></tr></thead><tbody>" + "".join(rows) + "</tbody></table></div>"


def _files(mm):
    out = []
    for f in (mm or {}).get("files") or []:
        out.append(f if isinstance(f, str) else (f.get("path") or f.get("name") or ""))
    return [x for x in out if x]


def _screen(chat):
    return chats.to_display(chat["msgs"]) if chat else []


def list_html(cid=None):
    """The conversations list: only names, each with a ⋯ button (the menu is drawn by CHAT_JS)."""
    rows = []
    for c in chats.list_chats():
        cls = "cm-row" + (" on" if c["id"] == cid else "")
        pin = "📌 " if c.get("pinned") else ""
        rows.append(f"<div class='{cls}' data-id='{c['id']}' data-pinned='{int(bool(c.get('pinned')))}' data-title='{_h.escape(c['title'], True)}'>"
                    f"<span class='cm-t'>{pin}{_h.escape(c['title'])}</span><button class='cm-dots' title='خيارات'>⋯</button></div>")
    return "<div class='cm-list'>" + ("".join(rows) or "<div class='empty'>ما فيه محادثات بعد</div>") + "</div>"


@safe
def send(cid, mm, model, fb):
    guard()
    text = ((mm or {}).get("text") or "").strip()
    paths = _files(mm)
    if not text and not paths:
        raise gr.Error("اكتب رسالتك أو أرفق ملف أولاً", title="الرسالة فاضية")
    chat = chats.load(cid) or chats.create(model)
    try:
        kept = [chats.keep_file(chat["id"], p) for p in paths]
    except ValueError as e:
        raise gr.Error(str(e), title="ملف غير مدعوم")
    chat["msgs"].append({"role": "user", "text": text, "files": kept})
    if chat["title"] == "محادثة جديدة":
        chat["title"] = (text or kept[0]["name"])[:40]
    route = priority.new_route("translate", model or priority.AUTO, bool(fb), max_wait=45)
    if not model or model == priority.AUTO:             # chat may use any key, in the translating priority order
        route = {**route, "order": priority.order_for("translate") or priority.order_for("edit")}
    recent = chat["msgs"][-24:]
    new_img = any(f["kind"] == "image" for f in kept)   # pictures are sent only with the message that carries them
    meta, avoid, answer = {}, set(), None
    try:
        with use_route(route):
            if new_img:                                     # find an AI that understands pictures
                api = chats.to_api(recent, SYSTEM, keep_images=1)
                for _ in range(5):
                    try:
                        answer = call(api, role="any", max_tokens=2048, temperature=0.7, task="chat", avoid=avoid, meta=meta)
                        break
                    except llm.BadRequest as e:
                        avoid.add(getattr(e, "key_id", ""))
                if answer is None:
                    chat["msgs"].pop()
                    raise gr.Error("ما لقيت ذكاء يقرأ الصور. النموذج اللي اخترته يقرأ النص فقط (مثل qwen2.5:7b). اختر Gemini أو Groq، أو في Ollama نزّل نموذج llava أو qwen2.5vl.",
                                   title="الصور غير مدعومة")
            else:                                           # later messages go to the AI you picked as plain text
                answer = call(chats.to_api(recent, SYSTEM, keep_images=0), role="any", max_tokens=2048, temperature=0.7, task="chat", meta=meta)
    except NoKeys as e:
        chat["msgs"].pop()
        raise gr.Error(str(e), title="ما فيه ذكاء يرد الآن")
    except llm.BadRequest as e:
        chat["msgs"].pop()
        raise gr.Error(f"الذكاء رفض الطلب: {e}", title="رفض الطلب")
    k = next((x for x in load_keys() if x["id"] == meta.get("key_id")), None)
    note = f"{meta.get('name', '?')} ({meta.get('model') or 'تلقائي'}) · {meta.get('secs', 0):.1f} ثانية" + (f" · {priority.brief_limit(k)}" if k else "")
    chat["msgs"].append({"role": "assistant", "text": answer, "note": note})
    chats.save(chat)
    if len({c["id"] for c in route["calls"]}) > 1:
        gr.Info("انتهى حد الذكاء السابق، فرد عليك التالي في ترتيب الأولوية.", title="🔁 تحوّل تلقائي")
    return chat["id"], _screen(chat), None, remaining_html(), list_html(chat["id"])


def new_chat():
    return None, [], None, list_html(None)


@safe
def act(cid, cmd):
    """One command from the list menu: open|id, pin|id, rename|id|new name, delete|id (the page already asked for confirmation)."""
    parts = (cmd or "").split("|", 2)
    if len(parts) < 2 or not parts[1]:
        return cid, gr.update(), list_html(cid)
    what, target = parts[0], parts[1]
    if what == "open":
        chat = chats.load(target)
        return (target if chat else None), _screen(chat), list_html(target if chat else None)
    if what == "pin":
        on = chats.toggle_pin(target)
        gr.Info("تم تثبيت المحادثة" if on else "أُلغي التثبيت", title="📌")
    elif what == "rename" and len(parts) == 3:
        chats.rename(target, parts[2])
    elif what == "delete":
        chats.delete(target)
        if target == cid:
            return None, [], list_html(None)
    return cid, gr.update(), list_html(cid)


def choices():
    return priority.choices("any", True, "حسب ترتيب الأولوية في الإعدادات")


CHAT_JS = """
(() => {
  const act = (cmd) => {
    const t = document.querySelector('#chat_cmd textarea, #chat_cmd input');
    const b = document.querySelector('#chat_go');
    if (!t || !b) return;
    t.value = cmd; t.dispatchEvent(new Event('input', {bubbles: true}));
    setTimeout(() => b.click(), 60);
  };
  const close = () => document.querySelectorAll('.cm-menu').forEach(m => m.remove());
  document.addEventListener('click', (e) => {
    const dots = e.target.closest('.cm-dots'), row = e.target.closest('.cm-row');
    const item = e.target.closest('.cm-menu button');
    if (item) {
      const id = item.dataset.id, a = item.dataset.a; close();
      if (a === 'rename') { const n = prompt('الاسم الجديد للمحادثة:', item.dataset.title); if (n && n.trim()) act('rename|' + id + '|' + n.trim()); }
      else if (a === 'delete') { if (confirm('تحذف هذي المحادثة؟ ما تقدر ترجعها بعد الحذف.')) act('delete|' + id); }
      else act('pin|' + id);
      return;
    }
    close();
    if (dots && row) {
      e.stopPropagation();
      const r = dots.getBoundingClientRect(), m = document.createElement('div');
      m.className = 'cm-menu'; const id = row.dataset.id, pinned = row.dataset.pinned === '1';
      m.innerHTML = `<button data-a="rename" data-id="${id}" data-title="">✏ تغيير الاسم</button>` +
        `<button data-a="pin" data-id="${id}">${pinned ? '📌 إلغاء التثبيت' : '📌 تثبيت المحادثة'}</button>` +
        `<button data-a="delete" data-id="${id}" class="danger">🗑 حذف</button>`;
      m.querySelector('[data-a=rename]').dataset.title = row.dataset.title;
      m.style.top = (r.bottom + 4) + 'px'; m.style.left = Math.max(8, Math.min(r.left, innerWidth - 190)) + 'px';
      document.body.appendChild(m);
    } else if (row) act('open|' + row.dataset.id);
  });
})();
"""


def toggle_menu(shown):
    return not shown, gr.update(visible=not shown)


def build():
    with gr.Tab("٥. 💬 تحدث مع الذكاء الاصطناعي") as tab:
        gr.HTML("<div class='step'><i>💬</i>تحدث مع الذكاء الاصطناعي في أي موضوع</div>"
                "<p class='hint'>كل محادثة تنحفظ، وتفتح القائمة (☰) وترجع لها. ترفع صور وملفات (pdf، txt، docx...). "
                "الذكاء هنا يكتب نص فقط: ما ينشئ صور ولا فيديو ولا صوت، والصوت والفيديو ما نقدر نرفعهم.</p>")
        cid = gr.State(None)
        shown = gr.State(False)
        with gr.Row(elem_classes="chat-top"):
            b_menu = gr.Button("☰", elem_classes="cm-burger", scale=0, min_width=52)
            model = gr.Dropdown(choices(), value="auto", label="أكلم", scale=3)
            fb = gr.Checkbox(True, label="إذا انتهى حده كمّل بترتيب الأولوية", scale=2)
        with gr.Row():
            with gr.Column(scale=1, min_width=240, visible=False, elem_classes="cm-side") as side:
                gr.Markdown("### المحادثات")
                b_new = gr.Button("➕ محادثة جديدة", variant="primary")
                hist = gr.HTML(list_html)
            with gr.Column(scale=3):
                chat = gr.Chatbot(height=480, rtl=True, show_label=False, render_markdown=True, sanitize_html=True, buttons=["copy"])
                box = gr.MultimodalTextbox(placeholder="اكتب رسالتك، أو ارفع صورة/ملف، ثم Enter", show_label=False, rtl=True, lines=2,
                                           file_count="multiple", file_types=["image", ".pdf", ".txt", ".md", ".csv", ".json", ".docx"])
        cmd = gr.Textbox(elem_id="chat_cmd", elem_classes="offscreen", label="cmd")
        go = gr.Button("go", elem_id="chat_go", elem_classes="offscreen")
        gr.Markdown("### المتبقي من حد كل ذكاء")
        left = gr.HTML(remaining_html())
    b_menu.click(toggle_menu, shown, [shown, side])
    box.submit(send, [cid, box, model, fb], [cid, chat, box, left, hist])
    b_new.click(new_chat, None, [cid, chat, box, hist])
    go.click(act, [cid, cmd], [cid, chat, hist])
    tab.select(lambda c: (gr.update(choices=choices()), remaining_html(), list_html(c)), cid, [model, left, hist])
    return {"model": model, "left": left}
