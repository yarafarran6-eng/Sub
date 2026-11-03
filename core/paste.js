() => {
  if (window.__subPaste) return;
  window.__subPaste = true;
  // When numbered-list text is copied from a chat website, the browser drops the numbers from the plain text.
  // The copied HTML still has them, so rebuild the numbering ("1_ text") before it lands in the Arabic box.
  function convert(html) {
    const doc = new DOMParser().parseFromString(html, "text/html");
    const lines = [];
    let cur = "", prefix = "";
    const flush = () => {
      const t = cur.replace(/\s+/g, " ").trim();
      if (t) { lines.push(prefix + t); prefix = ""; }
      cur = "";
    };
    const BLOCK = new Set(["P", "DIV", "BR", "H1", "H2", "H3", "H4", "H5", "H6", "BLOCKQUOTE", "TR", "PRE"]);
    const walk = (node) => {
      for (const ch of node.childNodes) {
        if (ch.nodeType === 3) { cur += ch.textContent; continue; }
        if (ch.nodeType !== 1) continue;
        const tag = ch.tagName;
        if (tag === "OL" || tag === "UL") {
          let n = parseInt(ch.getAttribute("start") || "1", 10);
          if (isNaN(n)) n = 1;
          flush();
          for (const li of ch.children) {
            if (li.tagName !== "LI") continue;
            flush();
            prefix = tag === "OL" ? (n++) + "_ " : "- ";
            walk(li);
            flush();
            prefix = "";
          }
        } else if (BLOCK.has(tag)) { flush(); walk(ch); flush(); }
        else walk(ch);
      }
    };
    walk(doc.body);
    flush();
    return lines.join("\n");
  }
  window.__subConvert = convert;
  document.addEventListener("paste", (e) => {
    const t = e.target;
    if (!t || t.tagName !== "TEXTAREA" || !t.closest(".arbox")) return;
    const cd = e.clipboardData;
    if (!cd) return;
    const html = cd.getData("text/html");
    if (!html || !/<ol[\s>]/i.test(html)) return;      // only when the copied content really was a numbered list
    const text = convert(html);
    if (!text) return;
    e.preventDefault();
    t.setRangeText(text, t.selectionStart, t.selectionEnd, "end");
    t.dispatchEvent(new Event("input", { bubbles: true }));
  }, true);
}
