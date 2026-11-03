"""What a unit does, taken from a public web page, before any donor is ranked.

Only the unit's name is sent out. Gift records stay on this machine. The text is used to see which
departments and themes already in the ledger are related, for example 資訊工程 and 教育.
"""
from __future__ import annotations

import ipaddress
import re
import unicodedata
from html import unescape
from urllib.parse import unquote, urljoin, urlparse

import httpx

from .. import i18n, org
from ..i18n import t

_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
_EDU = ("數位學習", "學習科技", "教育科技", "資訊教育", "學習科學", "數位教育")
_ABOUT = ("intro", "簡介", "about")
_CACHE: dict[str, dict] = {}


def departments_in_text(text: str) -> list[str]:
    """Preset departments named in a public page. Short aliases such as 物理 are ignored."""
    raw = unicodedata.normalize("NFKC", text or "")
    low = raw.lower()
    found = []
    for dept, _, aliases in org.DEPARTMENTS:
        hit = False
        for alias in (dept, *aliases):
            a = (alias or "").strip()
            if not a:
                continue
            if re.search(r"[\u4e00-\u9fff]", a):
                if len(a) >= 3 and a in raw:
                    hit = True
                    break
            elif len(a) >= 12 and re.search(r"\b" + re.escape(a.lower()) + r"\b", low):
                hit = True
                break
        if hit and dept not in found:
            found.append(dept)
    return found


def education_in_text(text: str) -> bool:
    raw = unicodedata.normalize("NFKC", text or "")
    return any(k in raw for k in _EDU)


def describe(info: dict) -> str:
    bits = [i18n.dept_label(d) for d in info.get("departments") or []]
    if info.get("education"):
        bits.append(t("agent.theme.education"))
    sep = "、" if i18n.current() == "zh-TW" else ", "
    return sep.join(b for b in bits if b)


def public_background(phrase: str) -> dict:
    """Search the public web for this unit and return related departments already in the ledger."""
    key = re.sub(r"\s+", "", unicodedata.normalize("NFKC", phrase or ""))
    if len(key) < 2:
        return {"ok": False, "departments": [], "education": False, "source": ""}
    if key in _CACHE:
        return _CACHE[key]
    info = _fetch(key)
    if info.get("ok") and (info["departments"] or info["education"]):
        _CACHE[key] = info
    return info


def _safe_url(url: str) -> bool:
    p = urlparse(url)
    if p.scheme not in ("http", "https"):
        return False
    host = (p.hostname or "").lower()
    if not host or host in ("localhost", "duckduckgo.com", "html.duckduckgo.com") or host.endswith(".duckduckgo.com"):
        return False
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return True
    return not (ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved)


def _plain(html: str) -> str:
    html = re.sub(r"(?is)<(script|style|noscript).*?>.*?</\1>", " ", html or "")
    html = re.sub(r"(?is)<[^>]+>", " ", html)
    return re.sub(r"\s+", " ", unescape(html))[:20000]


def _result_urls(html: str) -> list[str]:
    out = []
    for m in re.finditer(r"uddg=([^&\"']+)", html or ""):
        url = unquote(unescape(m.group(1)))
        if _safe_url(url) and url not in out:
            out.append(url)
    return out[:3]


def _about_link(html: str, base: str) -> str | None:
    host = urlparse(base).netloc
    found = []
    for m in re.finditer(r"(?is)<a[^>]*href=[\"']([^\"']+)[\"'][^>]*>(.*?)</a>", html or ""):
        href, text = unescape(m.group(1)), _plain(m.group(2))
        if not any(k in (href + text).lower() for k in _ABOUT):
            continue
        url = urljoin(base, href)
        if _safe_url(url) and urlparse(url).netloc == host and url.rstrip("/") != base.rstrip("/"):
            found.append(url)
    intro = next((u for u in found if "intro" in u.lower() or "簡介" in u), None)
    return intro or (found[0] if found else None)


def _get(client: httpx.Client, url: str) -> str:
    if not _safe_url(url):
        return ""
    try:
        r = client.get(url)
    except httpx.HTTPError:
        return ""
    if r.status_code >= 400:
        return ""
    final = str(r.url)
    if not _safe_url(final):
        return ""
    return r.text or ""


def _fetch(phrase: str) -> dict:
    empty = {"ok": False, "departments": [], "education": False, "source": ""}
    query = phrase if "中央" in phrase else f"{phrase} 中央大學"
    try:
        with httpx.Client(timeout=8.0, follow_redirects=True, headers={"User-Agent": _UA}) as client:
            try:
                r = client.get("https://html.duckduckgo.com/html/", params={"q": query})
                search = r.text if r.status_code < 400 else ""
            except httpx.HTTPError:
                search = ""
            pages: list[tuple[str, str]] = []
            for url in _result_urls(search):
                html = _get(client, url)
                if not html:
                    continue
                pages.append((url, html))
                about = _about_link(html, str(url))
                if about:
                    more = _get(client, about)
                    if more:
                        pages.append((about, more))
                if len(pages) >= 2:
                    break
    except httpx.HTTPError:
        return empty
    if not pages:
        return empty
    text = "\n".join(_plain(html) for _, html in pages)
    host = urlparse(pages[-1][0]).hostname or ""
    return {"ok": True, "departments": departments_in_text(text), "education": education_in_text(text), "source": host}
