"""Web search for the chat: finds pages and returns short readable extracts, so any AI (even a local one) can answer with sources.
Order: Tavily (if you put its key in Settings) -> DuckDuckGo page (free, no key, but can be blocked)."""
import html, os, re, urllib.parse
from concurrent.futures import ThreadPoolExecutor
import httpx
from .config import get_settings

UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"}


class SearchFailed(Exception):
    pass


def _clean(s):
    s = re.sub(r"(?is)<(script|style|nav|footer|header|noscript)[^>]*>.*?</\1>", " ", s)
    s = html.unescape(re.sub(r"(?s)<[^>]+>", " ", s))
    return re.sub(r"\s+", " ", s).strip()


def _ddg(query, n):
    try:
        r = httpx.post("https://html.duckduckgo.com/html/", data={"q": query}, headers=UA, timeout=12, follow_redirects=True)
    except httpx.HTTPError as e:
        raise SearchFailed(f"تعذّر الوصول لمحرك البحث: {e}")
    if r.status_code != 200 or "result__a" not in r.text:
        raise SearchFailed("محرك البحث المجاني رفض الطلب أو حدّ عدد البحث (جرّب بعد دقائق، أو ضع مفتاح Tavily في الإعدادات)")
    out = []
    for m in re.finditer(r'(?s)<a[^>]*class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>.*?(?:class="result__snippet"[^>]*>(.*?)</a>)?', r.text):
        url = html.unescape(m.group(1))
        if "uddg=" in url:
            url = urllib.parse.unquote(url.split("uddg=")[1].split("&")[0])
        if url.startswith("//"):
            url = "https:" + url
        out.append({"title": _clean(m.group(2)), "url": url, "snippet": _clean(m.group(3) or "")})
        if len(out) >= n:
            break
    return out


def _tavily(query, n, key):
    try:
        r = httpx.post("https://api.tavily.com/search", json={"api_key": key, "query": query, "max_results": n}, timeout=20)
    except httpx.HTTPError as e:
        raise SearchFailed(f"تعذّر الوصول لـTavily: {e}")
    if r.status_code != 200:
        raise SearchFailed(f"Tavily رفض الطلب ({r.status_code}). تأكد من المفتاح أو من الحد الشهري")
    return [{"title": x.get("title", ""), "url": x.get("url", ""), "snippet": x.get("content", "")} for x in r.json().get("results", [])][:n]


def _page(url, limit=2500):
    try:
        r = httpx.get(url, headers=UA, timeout=8, follow_redirects=True)
        if r.status_code == 200 and "html" in r.headers.get("content-type", ""):
            return _clean(r.text)[:limit]
    except Exception:
        pass
    return ""


def search(query, n=5, read_pages=3):
    """-> list of {title,url,snippet,text}. Raises SearchFailed with a reason you can show."""
    query = re.sub(r"\s+", " ", query or "").strip()[:250]
    if not query:
        raise SearchFailed("ما فيه نص للبحث")
    if os.getenv("SUB_MOCK_SEARCH"):
        return [{"title": f"نتيجة {i}", "url": f"https://example.com/{i}", "snippet": f"ملخص {i} عن {query}", "text": f"نص الصفحة {i}"} for i in range(1, 4)]
    key = (get_settings().get("tavily_key") or "").strip()
    res = _tavily(query, n, key) if key else _ddg(query, n)
    if not res:
        raise SearchFailed("ما لقيت نتائج لهذا البحث")
    with ThreadPoolExecutor(max_workers=3) as ex:
        texts = list(ex.map(_page, [r["url"] for r in res[:read_pages]]))
    for i, r in enumerate(res):
        r["text"] = texts[i] if i < len(texts) else ""
    return res


def as_context(results):
    """The block added to the question: numbered sources, to answer from and cite as [1], [2]."""
    parts = []
    for i, r in enumerate(results, 1):
        parts.append(f"[{i}] {r['title']}\nURL: {r['url']}\n{r['snippet']}\n{r.get('text', '')}".strip())
    return ("\n\n---- نتائج بحث الويب (مصادر) ----\n" + "\n\n".join(parts) +
            "\n---- نهاية النتائج ----\nاعتمد على هذه النتائج في الإجابة واذكر رقم المصدر مثل [1]. إذا ما كفت قل ذلك بوضوح ولا تخترع معلومات.")
