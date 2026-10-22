"""联网检索：必应中国（免费无 key，大陆可直连），失败返回空串自动降级。"""
import html as html_mod
import re

import requests

import config

_UA = {"User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                      "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36")}
_TAG_RE = re.compile(r"<[^>]+>")
_ALGO_RE = re.compile(r'<li class="b_algo".*?<h2[^>]*><a[^>]*>(.*?)</a></h2>(.*?)</li>', re.S)
_P_RE = re.compile(r"<p[^>]*>(.*?)</p>", re.S)


def _clean(s: str) -> str:
    return re.sub(r"\s+", " ", _TAG_RE.sub("", html_mod.unescape(s))).strip()


def search(query: str, k: int = 4) -> str:
    """返回 '标题：摘要' 每行一条；失败/无结果返回 ''。"""
    if not (config.SEARCH_ENABLED and query.strip()):
        return ""
    try:
        r = requests.get("https://cn.bing.com/search", params={"q": query.strip()},
                         headers=_UA, timeout=config.SEARCH_TIMEOUT)
        lines = []
        for title, rest in _ALGO_RE.findall(r.text)[:k]:
            t = _clean(title)
            s = ""
            for p in _P_RE.findall(rest):
                s = _clean(p)
                if s:
                    break
            if t:
                lines.append(f"- {t}：{s[:100]}")
        return "\n".join(lines)
    except Exception:
        return ""
