"""Where things are in the system. The analyst uses this to answer "where do I find ..." and to put an Open button under an answer.
Titles and descriptions live in the locale catalogues (feat.<id>.title / what / how) so they follow the interface language."""
from __future__ import annotations

from urllib.parse import urlencode

from ..i18n import t

# id, route, search words (English and 繁體中文)
FEATURES: list[tuple[str, str, tuple[str, ...]]] = [
    ("overview", "/", ("overview", "dashboard", "total", "trend", "chart", "how much", "giving", "download", "export", "總覽", "總額", "趨勢", "圖表", "下載", "匯出")),
    ("bridge", "/#change", ("why", "change", "changed", "waterfall", "bridge", "difference", "為何", "為什麼", "變化", "改變", "差異")),
    ("concentration", "/#concentration", ("concentrat", "top donors", "few donors", "depend", "biggest donor", "集中", "少數", "依賴")),
    ("seasonality", "/#when", ("month", "busiest", "season", "peak", "when do", "timing", "月份", "每個月", "每月", "高峰", "旺季", "淡季", "什麼時候", "時間")),
    ("journey", "/journey", ("retention", "retain", "new donor", "lapsed", "come back", "funnel", "second gift", "留存", "回流", "流失", "首次", "第二次")),
    ("risk", "/risk", ("at risk", "at-risk", "stop giving", "lapse", "call list", "phone", "call", "風險", "停止", "致電", "電話", "流失")),
    ("matching", "/matching", ("prospect", "who to ask", "who should we ask", "invite", "match", "target", "配對", "邀請", "潛在", "誰")),
    ("briefs", "/briefs", ("brief", "appeal", "letter", "draft", "ask amount", "pitch", "簡報", "募款信", "草稿", "擬稿")),
    ("strategy", "/strategy", ("what if", "scenario", "simulate", "simulation", "goal", "raise", "target amount", "情境", "模擬", "策略", "目標", "試算")),
    ("roll", "/roll", ("roll", "thank", "recognition", "anonymous", "acknowledg", "芳名錄", "感謝", "匿名", "表揚")),
    ("data_upload", "/data?tab=upload", ("upload", "import", "excel", "spreadsheet", "columns", "mapping", "上傳", "匯入", "欄位", "試算表")),
    ("data_reference", "/data?tab=reference", ("project table", "classification", "classify", "categories", "category", "專案對照表", "分類", "類別")),
    ("data_review", "/data?tab=review", ("review queue", "unsure", "confirm label", "pending", "待審", "確認", "標籤")),
    ("assistant", "/ai", ("assistant", "ask ai", "chat", "analyst", "助理", "提問", "分析助理")),
]
BY_ID = {f[0]: f for f in FEATURES}


def title(fid: str) -> str:
    return t(f"feat.{fid}.title")


def route(fid: str, **params) -> str:
    base = BY_ID[fid][1]
    if not params:
        return base
    path, _, frag = base.partition("#")
    sep = "&" if "?" in path else "?"
    return f"{path}{sep}{urlencode(params)}" + (f"#{frag}" if frag else "")


def link(fid: str, **params) -> dict:
    return {"label": t("agent.open", page=title(fid)), "to": route(fid, **params)}


def search(query: str, limit: int = 3) -> list[str]:
    """Feature ids best matching the words in a question (all of them, in menu order, when nothing matches or no query)."""
    q = (query or "").lower().strip()
    if not q:
        return [f[0] for f in FEATURES]
    scored = []
    for fid, _to, words in FEATURES:
        s = sum(2 if w in q else 0 for w in words) + sum(1 for part in q.split() if len(part) > 3 and part in (title(fid) + " " + t(f"feat.{fid}.what")).lower())
        if s:
            scored.append((s, fid))
    scored.sort(key=lambda x: -x[0])
    best = scored[0][0] if scored else 0
    keep = [fid for s, fid in scored if s >= max(1, best / 2)][:limit]       # only the clear matches, not every page that shares a word
    return keep or [f[0] for f in FEATURES]


def describe(fid: str) -> dict:
    return {"id": fid, "name": title(fid), "what_it_answers": t(f"feat.{fid}.what"), "how_to_use": t(f"feat.{fid}.how")}
