() => {
  if (window.__subDrop) return;
  window.__subDrop = true;
  // Three ways to give the page-replacement picture: the file button (already there), paste, drag and drop.
  // Paste and drop both end in the file button's own <input type=file>, so the server side is one single path.
  const ZONE = "#cp_zone";
  const findInput = () =>                                            // the file button's hidden <input>, wherever Gradio put it
    document.querySelector("#cp_up input[type=file]") || document.querySelector("#cp_up")?.parentElement?.querySelector("input[type=file]")
    || Array.from(document.querySelectorAll("input[type=file]")).find((i) => /png|jpe?g|webp|image/i.test(i.accept || ""));
  const note = (t, bad) => {
    const z = document.querySelector(ZONE + " .dz-msg");
    if (z) { z.textContent = t; z.classList.toggle("dz-bad", !!bad); }
  };
  const feed = (file) => {
    const input = findInput();
    if (!input) return note("ما لقيت خانة الرفع، افتح «إدارة هذي الصفحة» أولاً", true);
    if (!file || !/^image\//.test(file.type || "")) return note("هذا مو ملف صورة. اختر صورة PNG أو JPG أو WEBP", true);
    let f = file;
    if (!/\.(png|jpe?g|webp)$/i.test(f.name || "")) {
      const ext = (f.type.split("/")[1] || "png").replace("jpeg", "jpg");
      f = new File([file], "صورة_ملصوقة." + ext, { type: file.type });
    }
    const dt = new DataTransfer();
    dt.items.add(f);
    input.files = dt.files;
    input.dispatchEvent(new Event("change", { bubbles: true }));
    note("✅ وصلت الصورة، تحقق منها تحت ثم اضغط «استبدل»");
  };
  const visible = () => { const z = document.querySelector(ZONE); return z && z.offsetParent !== null; };
  const imgOf = (list) => Array.from(list || []).find((f) => /^image\//.test(f.type || ""));

  document.addEventListener("dragover", (e) => {
    const z = e.target.closest && e.target.closest(ZONE);
    if (z) { e.preventDefault(); z.classList.add("dz-on"); }
  });
  document.addEventListener("dragleave", (e) => {
    const z = e.target.closest && e.target.closest(ZONE);
    if (z) z.classList.remove("dz-on");
  });
  document.addEventListener("drop", (e) => {
    const z = e.target.closest && e.target.closest(ZONE);
    if (!z) return;
    e.preventDefault();
    z.classList.remove("dz-on");
    const files = e.dataTransfer && e.dataTransfer.files;
    if (!files || !files.length) return note("ما وصل ملف. اسحب الصورة من مجلد أو من سطح المكتب", true);
    feed(files[0]);
  });
  document.addEventListener("paste", (e) => {                       // Ctrl+V anywhere on the page while the zone is open
    if (!visible() || (e.target.closest && e.target.closest("#chat_in"))) return;
    const f = imgOf(e.clipboardData && e.clipboardData.files);
    if (f) { e.preventDefault(); feed(f); }
  });
  document.addEventListener("click", async (e) => {
    if (!(e.target.closest && e.target.closest("#cp_paste_btn"))) return;
    try {
      const items = await navigator.clipboard.read();
      for (const it of items) {
        const t = it.types.find((x) => x.startsWith("image/"));
        if (t) return feed(new File([await it.getType(t)], "image", { type: t }));
      }
      note("ما في صورة منسوخة. انسخ صورة أولاً (كليك يمين ← نسخ الصورة) ثم جرّب", true);
    } catch (err) {
      note("المتصفح ما سمح بقراءة الحافظة. اضغط Ctrl+V بدل الزر", true);
    }
  });
}
