"""Tab 5: chat with the AIs about anything. Pick one, switch any time; when its limit ends the next one in your priority answers."""
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


def _list(cid):
    return gr.update(choices=chats.choices(), value=cid)


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
    has_img = any(f["kind"] == "image" for m in recent[-6:] for f in m.get("files", []))
    meta, avoid, answer, stripped = {}, set(), None, False
    try:
        with use_route(route):
            if has_img:                                      # pictures in the recent messages: find an AI that understands them
                api = chats.to_api(recent, SYSTEM)
                for _ in range(5):
                    try:
                        answer = call(api, role="any", max_tokens=2048, temperature=0.7, task="chat", avoid=avoid, meta=meta)
                        break
                    except llm.BadRequest as e:
                        avoid.add(getattr(e, "key_id", ""))
            if answer is None:
                if has_img and any(f["kind"] == "image" for f in kept):
                    chat["msgs"].pop()                       # the new message itself has a picture and nobody can read it
                    raise gr.Error("الذكاء اللي اخترته يقرأ النص فقط ولا يفهم الصور (مثل qwen2.5:7b). اختر ذكاء يدعم الصور مثل Gemini، أو في Ollama نزّل نموذج llava أو qwen2.5vl.",
                                   title="الصور غير مدعومة")
                # no picture in the new message: answer from the text only (the earlier answer already describes the picture)
                stripped = has_img
                answer = call(chats.to_api(recent, SYSTEM, keep_images=0), role="any", max_tokens=2048, temperature=0.7, task="chat", meta=meta)
    except NoKeys as e:
        chat["msgs"].pop()
        raise gr.Error(str(e), title="ما فيه ذكاء يرد الآن")
    except llm.BadRequest as e:
        chat["msgs"].pop()
        raise gr.Error(f"الذكاء رفض الطلب: {e}", title="رفض الطلب")
    k = next((x for x in load_keys() if x["id"] == meta.get("key_id")), None)
    note = f"{meta.get('name', '?')} ({meta.get('model') or 'تلقائي'}) · {meta.get('secs', 0):.1f} ثانية" + (f" · {priority.brief_limit(k)}" if k else "")
    if stripped:
        note += " · رد من النص فقط (هذا الذكاء ما يشوف الصور)"
    chat["msgs"].append({"role": "assistant", "text": answer, "note": note})
    chats.save(chat)
    if len({c["id"] for c in route["calls"]}) > 1:
        gr.Info("انتهى حد الذكاء السابق، فرد عليك التالي في ترتيب الأولوية.", title="🔁 تحوّل تلقائي")
    return chat["id"], _screen(chat), None, remaining_html(), _list(chat["id"])


def new_chat():
    return None, [], None, _list(None), ""


def open_chat(cid):
    chat = chats.load(cid)
    return (cid if chat else None), _screen(chat), (chat or {}).get("title", "")


@safe
def delete_chat(cid, ok):
    if not cid:
        raise gr.Error("افتح محادثة أولاً", title="ما فيه محادثة")
    if not ok:
        raise gr.Error("علّم مربع «أأكد الحذف» أولاً", title="لم يتم الحذف")
    chats.delete(cid)
    return None, [], _list(None), False, ""


@safe
def rename_chat(cid, title):
    if not cid:
        raise gr.Error("افتح محادثة أولاً", title="ما فيه محادثة")
    chats.rename(cid, title)
    return _list(cid)


def choices():
    return priority.choices("any", True, "حسب ترتيب الأولوية في الإعدادات")


def build():
    with gr.Tab("٥. 💬 تحدث مع الذكاء الاصطناعي") as tab:
        gr.HTML("<div class='step'><i>💬</i>تحدث مع الذكاء الاصطناعي في أي موضوع</div>"
                "<p class='hint'>كل محادثة تنحفظ، وتقدر ترجع لها من القائمة. ترفع صور وملفات (pdf، txt، docx...). "
                "الذكاء هنا يكتب نص فقط: ما ينشئ صور ولا فيديو ولا صوت، والصوت والفيديو ما نقدر نرفعهم.</p>")
        cid = gr.State(None)
        with gr.Row():
            with gr.Column(scale=1, min_width=230):
                b_new = gr.Button("➕ محادثة جديدة", variant="primary")
                hist = gr.Dropdown(chats.choices(), value=None, label="المحادثات السابقة", info="اختر محادثة لتفتحها")
                title = gr.Textbox(label="اسم المحادثة", lines=1, rtl=True)
                b_ren = gr.Button("✏ غيّر الاسم", size="sm")
                with gr.Row():
                    ok = gr.Checkbox(False, label="أأكد الحذف")
                    b_del = gr.Button("🗑 احذف", size="sm", variant="stop")
            with gr.Column(scale=3):
                with gr.Row():
                    model = gr.Dropdown(choices(), value="auto", label="أكلم", scale=3)
                    fb = gr.Checkbox(True, label="إذا انتهى حده كمّل بترتيب الأولوية", scale=2)
                chat = gr.Chatbot(height=480, rtl=True, show_label=False, render_markdown=True, sanitize_html=True, buttons=["copy"])
                box = gr.MultimodalTextbox(placeholder="اكتب رسالتك، أو ارفع صورة/ملف، ثم Enter", show_label=False, rtl=True, lines=2,
                                           file_count="multiple", file_types=["image", ".pdf", ".txt", ".md", ".csv", ".json", ".docx"])
        gr.Markdown("### المتبقي من حد كل ذكاء")
        left = gr.HTML(remaining_html())
    box.submit(send, [cid, box, model, fb], [cid, chat, box, left, hist])
    b_new.click(new_chat, None, [cid, chat, box, hist, title])
    hist.input(open_chat, hist, [cid, chat, title])
    b_ren.click(rename_chat, [cid, title], hist)
    b_del.click(delete_chat, [cid, ok], [cid, chat, hist, ok, title])
    tab.select(lambda: (gr.update(choices=choices()), remaining_html(), _list(None) if False else gr.update(choices=chats.choices())), None, [model, left, hist])
    return {"model": model, "left": left}
