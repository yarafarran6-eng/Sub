"""Tab 5: chat with the AIs. Saved chats (☰ list with ⋯ menu), pictures/files, web search, your novels as context,
private mode (local AI only), reply styles, regenerate / edit last message, export, compare two AIs, voice."""
import html as _h
import time
import gradio as gr
from core import chatctx, chats, llm, priority, websearch
from core.keystore import load_keys
from core.pool import AllBusy, NoKeys, POOL, call, kname, use_route
from .common import guard, safe

SYSTEM = ("You are a helpful assistant inside a translation app. Always reply in the same language as the user's last message. "
          "If the user writes Arabic, reply in simple, clear Arabic (plain words, no unneeded English, never Chinese or any other language unless the user asks). "
          "Format with simple Markdown: short paragraphs, bullet lists when listing, code only inside code blocks. "
          "Do not add signatures or notes about yourself. If you cannot do something (for example create images, video or audio), say so briefly and suggest what you can do instead.")
STYLES = {
    "عادي": "",
    "مترجم أدبي": "Act as a literary translator and editor. Prefer natural, elegant Arabic that keeps the author's voice; explain a choice only when asked.",
    "مدقق لغوي": "Act as a strict Arabic proofreader. Return the corrected text first, then a short list of what you changed and why.",
    "يشرح ببساطة": "Explain everything very simply, with short sentences and a small example, as if to a beginner.",
    "مختصر جداً": "Answer in as few words as possible: the answer first, no introduction.",
}


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



def is_local(k):
    b = (k.get("base") or "").lower()
    return k.get("provider") == "ollama" or any(x in b for x in ("localhost", "127.0.0.1", "[::1]")) or k.get("key", "").startswith("mock-local")


def local_ids():
    return [k["id"] for k in load_keys() if k.get("enabled") and is_local(k)]


def _files(mm):
    out = []
    for f in (mm or {}).get("files") or []:
        out.append(f if isinstance(f, str) else (f.get("path") or f.get("name") or ""))
    return [x for x in out if x]


def _screen(chat):
    return chats.to_display(chat["msgs"]) if chat else []


def list_html(cid=None, q=""):
    """The conversations list: only names, each with a ⋯ button (the menu is drawn by CHAT_JS)."""
    rows = []
    for c in chats.search(q):
        cls = "cm-row" + (" on" if c["id"] == cid else "")
        pin = ("📌 " if c.get("pinned") else "") + ("🔒 " if c.get("private") else "")
        rows.append(f"<div class='{cls}' data-id='{c['id']}' data-pinned='{int(bool(c.get('pinned')))}' data-title='{_h.escape(c['title'], True)}'>"
                    f"<span class='cm-t'>{pin}{_h.escape(c['title'])}</span><button class='cm-dots' title='خيارات'>⋯</button></div>")
    return "<div class='cm-list'>" + ("".join(rows) or "<div class='empty'>ما فيه محادثات</div>") + "</div>"


def _route(model, fb, priv):
    if priv:
        ids = local_ids()
        if not ids:
            raise gr.Error("المحادثة الخاصة تحتاج ذكاء محلي (أولاما) مضاف ومفعّل في تبويب المفاتيح. ما لقيت واحد، فما أرسلت شي لأي خدمة خارجية.", title="ما فيه ذكاء محلي")
        pick = model if model in ids else ids[0]
        return {"order": [pick], "only": True, "max_wait": 45, "calls": []}
    route = priority.new_route("translate", model or priority.AUTO, bool(fb), max_wait=45)
    if not model or model == priority.AUTO:             # chat may use any key, in the translating priority order
        route = {**route, "order": priority.order_for("translate") or priority.order_for("edit")}
    return route


def _inject(api, block):
    last = api[-1]
    if isinstance(last["content"], str):
        last["content"] += block
    else:
        for b in last["content"]:
            if b.get("type") == "text":
                b["text"] += block
                break


def _answer(chat, new_img, model, fb, priv, style, web, proj):
    """Asks the AI about the last message of `chat`. Returns (answer, meta, sources, route). Raises gr.Error with the cause."""
    route = _route(model, fb, priv)
    last_text = chat["msgs"][-1].get("text", "")
    system = SYSTEM + ("\n\n" + STYLES[style] if STYLES.get(style) else "")
    if proj:
        system += chatctx.project_context(proj, last_text)
    recent = chat["msgs"][-24:]
    sources, block = [], ""
    if web and not priv:
        try:
            res = websearch.search(last_text)
            sources = [{"title": r["title"] or r["url"], "url": r["url"]} for r in res]
            block = websearch.as_context(res)
        except websearch.SearchFailed as e:
            gr.Warning(f"{e}. رديت بدون بحث.", title="🌐 البحث ما اشتغل")
    api = chats.to_api(recent, system, keep_images=1 if new_img else 0)
    if block:
        _inject(api, block)
    meta, avoid, answer = {}, set(), None
    with use_route(route):
        if new_img:                                     # find an AI that understands pictures
            for _ in range(5):
                try:
                    answer = call(api, role="any", max_tokens=2048, temperature=0.7, task="chat", avoid=avoid, meta=meta)
                    break
                except llm.BadRequest as e:
                    avoid.add(getattr(e, "key_id", ""))
            if answer is None:
                raise gr.Error("ما لقيت ذكاء يقرأ الصور. النموذج اللي اخترته يقرأ النص فقط (مثل qwen2.5:7b). اختر Gemini أو Groq، أو في Ollama نزّل نموذج llava أو qwen2.5vl.",
                               title="الصور غير مدعومة")
        else:                                           # later messages go to the AI you picked, as plain text
            answer = call(api, role="any", max_tokens=2048, temperature=0.7, task="chat", meta=meta)
    return answer, meta, sources, route


def _finish(chat, answer, meta, sources, route, priv):
    k = next((x for x in load_keys() if x["id"] == meta.get("key_id")), None)
    note = f"{meta.get('name', '?')} ({meta.get('model') or 'تلقائي'}) · {meta.get('secs', 0):.1f} ثانية" + (f" · {priority.brief_limit(k)}" if k else "")
    if priv:
        note += " · 🔒 خاصة، ما خرج شي من جهازك"
    m = {"role": "assistant", "text": answer, "note": note}
    if sources:
        m["sources"] = sources
    chat["msgs"].append(m)
    chats.save(chat)
    if len({c["id"] for c in route["calls"]}) > 1:
        gr.Info("انتهى حد الذكاء السابق، فرد عليك التالي في ترتيب الأولوية.", title="🔁 تحوّل تلقائي")


def _run(chat, new_img, model, fb, priv, style, web, proj):
    try:
        answer, meta, sources, route = _answer(chat, new_img, model, fb, priv, style, web, proj)
    except NoKeys as e:
        chat["msgs"].pop()
        raise gr.Error(str(e), title="ما فيه ذكاء يرد الآن")
    except llm.BadRequest as e:
        chat["msgs"].pop()
        raise gr.Error(f"الذكاء رفض الطلب: {e}", title="رفض الطلب")
    except gr.Error:
        chat["msgs"].pop()
        raise
    _finish(chat, answer, meta, sources, route, priv)


@safe
def send(cid, mm, model, fb, priv, style, web, proj):
    guard()
    text = ((mm or {}).get("text") or "").strip()
    paths = _files(mm)
    if not text and not paths:
        raise gr.Error("اكتب رسالتك أو أرفق ملف أولاً", title="الرسالة فاضية")
    chat = chats.load(cid) or chats.create(model)
    if priv:
        chat["private"] = True
    try:
        kept = [chats.keep_file(chat["id"], p) for p in paths]
    except ValueError as e:
        raise gr.Error(str(e), title="ملف غير مدعوم")
    chat["msgs"].append({"role": "user", "text": text, "files": kept})
    if chat["title"] == "محادثة جديدة":
        chat["title"] = (text or kept[0]["name"])[:40]
    _run(chat, any(f["kind"] == "image" for f in kept), model, fb, bool(priv or chat.get("private")), style, web, proj)
    return chat["id"], _screen(chat), None, remaining_html(), list_html(chat["id"])


@safe
def regenerate(cid, model, fb, priv, style, web, proj):
    """Throws away the last answer and asks again (maybe with another AI)."""
    chat = chats.load(cid)
    if not chat or len(chat["msgs"]) < 2 or chat["msgs"][-1]["role"] != "assistant":
        raise gr.Error("ما فيه رد تعيد توليده", title="لا يوجد رد")
    chat["msgs"].pop()
    new_img = any(f["kind"] == "image" for f in chat["msgs"][-1].get("files", []))
    _run(chat, new_img, model, fb, bool(priv or chat.get("private")), style, web, proj)
    return _screen(chat), remaining_html(), list_html(cid)


@safe
def edit_last(cid):
    """Takes your last message back into the box so you can change it and send again."""
    chat = chats.load(cid)
    if not chat:
        raise gr.Error("افتح محادثة أولاً", title="ما فيه محادثة")
    while chat["msgs"] and chat["msgs"][-1]["role"] == "assistant":
        chat["msgs"].pop()
    if not chat["msgs"]:
        raise gr.Error("ما فيه رسالة تعدّلها", title="لا توجد رسالة")
    last = chat["msgs"].pop()
    chats.save(chat)
    return _screen(chat), {"text": last.get("text", ""), "files": [f["path"] for f in last.get("files", [])]}, list_html(cid)


def new_chat():
    return None, [], None, list_html(None), False


@safe
def act(cid, cmd):
    """One command from the list menu: open|id, pin|id, rename|id|new name, delete|id (the page already asked for confirmation)."""
    parts = (cmd or "").split("|", 2)
    if len(parts) < 2 or not parts[1]:
        return cid, gr.update(), list_html(cid), gr.update()
    what, target = parts[0], parts[1]
    if what == "open":
        chat = chats.load(target)
        return (target if chat else None), _screen(chat), list_html(target if chat else None), bool((chat or {}).get("private"))
    if what == "pin":
        on = chats.toggle_pin(target)
        gr.Info("تم تثبيت المحادثة" if on else "أُلغي التثبيت", title="📌")
    elif what == "rename" and len(parts) == 3:
        chats.rename(target, parts[2])
    elif what == "delete":
        chats.delete(target)
        if target == cid:
            return None, [], list_html(None), False
    return cid, gr.update(), list_html(cid), gr.update()


def filter_list(cid, q):
    return list_html(cid, q)


@safe
def export(cid):
    chat = chats.load(cid)
    if not chat:
        raise gr.Error("افتح محادثة أولاً", title="ما فيه محادثة")
    return gr.update(value=chats.export_md(chat), visible=True)


@safe
def compare(text, a, b):
    guard()
    text = (text or "").strip()
    if not text:
        raise gr.Error("اكتب السؤال أولاً", title="السؤال فاضي")
    if not a or not b or a == b:
        raise gr.Error("اختر ذكاءين مختلفين", title="اختيار ناقص")
    outs = []
    for kid in (a, b):
        route = {"order": [kid], "only": True, "max_wait": 45, "calls": []}
        meta = {}
        try:
            with use_route(route):
                ans = call([{"role": "system", "content": SYSTEM}, {"role": "user", "content": text}], role="any", max_tokens=2048,
                           temperature=0.7, task="chat", meta=meta)
            outs.append(f"**{meta.get('name', '?')} ({meta.get('model') or 'تلقائي'}) · {meta.get('secs', 0):.1f} ثانية**\n\n{ans}")
        except (NoKeys, llm.BadRequest, RuntimeError) as e:
            outs.append(f"⚠ هذا الذكاء ما رد: {e}")
    return outs[0], outs[1]


def choices():
    return priority.choices("any", True, "حسب ترتيب الأولوية في الإعدادات")


def key_choices():
    return [c for c in priority.choices("any", False)]


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
  const isAr = (s) => /[\\u0600-\\u06FF]/.test(s);
  let rec = null;
  document.addEventListener('click', (e) => {
    const dots = e.target.closest('.cm-dots'), row = e.target.closest('.cm-row');
    const item = e.target.closest('.cm-menu button');
    const mic = e.target.closest('.cm-mic'), spk = e.target.closest('.cm-speak');
    if (mic) {                                   // dictation: the browser's own speech recognition (Chrome, Edge, Brave)
      const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
      if (!SR) { alert('متصفحك ما يدعم الكتابة بالصوت. جرّب Chrome أو Edge.'); return; }
      if (rec) { rec.stop(); rec = null; mic.classList.remove('on'); return; }
      rec = new SR(); rec.lang = 'ar-SA'; rec.interimResults = false; rec.continuous = false;
      mic.classList.add('on');
      rec.onresult = (ev) => {
        const ta = document.querySelector('#chat_in textarea'); if (!ta) return;
        ta.value = (ta.value ? ta.value + ' ' : '') + ev.results[0][0].transcript;
        ta.dispatchEvent(new Event('input', {bubbles: true}));
      };
      rec.onend = () => { rec = null; mic.classList.remove('on'); };
      rec.onerror = () => { rec = null; mic.classList.remove('on'); };
      rec.start(); return;
    }
    if (spk) {                                   // read the last answer aloud with the browser's voice
      if (speechSynthesis.speaking) { speechSynthesis.cancel(); return; }
      const msgs = document.querySelectorAll('#chat_bot .bot, #chat_bot [data-testid="bot"]');
      if (!msgs.length) return;
      const clone = msgs[msgs.length - 1].cloneNode(true);
      clone.querySelectorAll('sub, button').forEach(x => x.remove());
      const txt = clone.innerText.trim(); if (!txt) return;
      const u = new SpeechSynthesisUtterance(txt); u.lang = isAr(txt) ? 'ar-SA' : 'en-US';
      speechSynthesis.speak(u); return;
    }
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
            priv = gr.Checkbox(False, label="🔒 محادثة خاصة (أولاما فقط)", info="ما يخرج شي من جهازك", scale=2)
        with gr.Row():
            style = gr.Dropdown(list(STYLES), value="عادي", label="أسلوب الرد", scale=2)
            web = gr.Checkbox(False, label="🌐 ابحث في الويب", info="يرسل نص سؤالك لمحرك البحث", scale=2)
            proj = gr.Dropdown(chatctx.projects(), value="", label="📚 اعتمد على روايتي", scale=3)
        with gr.Row():
            with gr.Column(scale=1, min_width=240, visible=False, elem_classes="cm-side") as side:
                gr.Markdown("### المحادثات")
                b_new = gr.Button("➕ محادثة جديدة", variant="primary")
                q = gr.Textbox(placeholder="🔍 ابحث في المحادثات", show_label=False, lines=1, rtl=True)
                hist = gr.HTML(list_html)
            with gr.Column(scale=3):
                chat = gr.Chatbot(height=480, rtl=True, show_label=False, render_markdown=True, sanitize_html=True, buttons=["copy"], elem_id="chat_bot")
                box = gr.MultimodalTextbox(placeholder="اكتب رسالتك، أو ارفع صورة/ملف، ثم Enter (سطر جديد: Shift+Enter)", show_label=False, rtl=True, lines=1, max_lines=8, elem_id="chat_in",
                                           file_count="multiple", file_types=["image", ".pdf", ".txt", ".md", ".csv", ".json", ".docx"])
                with gr.Row():
                    gr.HTML("<button class='cm-tool cm-mic' type='button'>🎤 اكتب بصوتك</button><button class='cm-tool cm-speak' type='button'>🔊 اقرأ آخر رد</button>")
                    b_regen = gr.Button("🔄 أعد التوليد", size="sm")
                    b_edit = gr.Button("✏ عدّل آخر رسالة", size="sm")
                    b_exp = gr.Button("📤 صدّر المحادثة", size="sm")
                out_file = gr.File(label="ملف المحادثة", visible=False)
        with gr.Accordion("⚖ قارن بين ذكاءين", open=False):
            gr.HTML("<p class='hint'>اكتب سؤال واحد وشوف رد ذكاءين لهم جنب بعض. (ما ينحفظ في المحادثات.)</p>")
            cq = gr.Textbox(label="السؤال", lines=2, rtl=True)
            with gr.Row():
                ca = gr.Dropdown(key_choices(), label="الذكاء الأول")
                cb = gr.Dropdown(key_choices(), label="الذكاء الثاني")
            b_cmp = gr.Button("قارن", variant="primary")
            with gr.Row():
                ra = gr.Markdown()
                rb = gr.Markdown()
        cmd = gr.Textbox(elem_id="chat_cmd", elem_classes="offscreen", label="cmd")
        go = gr.Button("go", elem_id="chat_go", elem_classes="offscreen")
        gr.Markdown("### المتبقي من حد كل ذكاء")
        left = gr.HTML(remaining_html())
    opts = [model, fb, priv, style, web, proj]
    b_menu.click(toggle_menu, shown, [shown, side])
    box.submit(send, [cid, box] + opts, [cid, chat, box, left, hist])
    b_new.click(new_chat, None, [cid, chat, box, hist, priv])
    go.click(act, [cid, cmd], [cid, chat, hist, priv])
    q.input(filter_list, [cid, q], hist)
    b_regen.click(regenerate, [cid] + opts, [chat, left, hist])
    b_edit.click(edit_last, cid, [chat, box, hist])
    b_exp.click(export, cid, out_file)
    b_cmp.click(compare, [cq, ca, cb], [ra, rb])
    tab.select(lambda c: (gr.update(choices=choices()), remaining_html(), list_html(c), gr.update(choices=chatctx.projects()),
                          gr.update(choices=key_choices()), gr.update(choices=key_choices())), cid, [model, left, hist, proj, ca, cb])
    return {"model": model, "left": left}
