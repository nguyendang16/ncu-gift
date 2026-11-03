"""WP5: opportunity identification and donor matching ("CauseMatch").

Direction used by the dashboard: given a target (purpose category, department or
project) rank donors by affinity, with an evidence card per donor. Scores are
bounded, additive and fully inspectable; weights are constants below.

Evaluation (design from the plan): temporal holdout at purpose-category and
department level. History up to year T-1, ask who gives to each target in year T,
compare with baselines. New-project matching is shown as a qualitative case study.
"""
from __future__ import annotations

import re
import unicodedata

import numpy as np
import pandas as pd

from .. import i18n, org
from ..i18n import t
from .frame import InsufficientData, cash, years_of

WEIGHTS = {"direct": 3.0, "unit": 2.0, "college": 1.0, "sub": 1.5, "active": 0.8, "capacity": 0.4}
MAX_SCORE = sum(WEIGHTS.values())


def _mask(df: pd.DataFrame, kind: str, name: str) -> pd.Series:
    col = {"sub": "purpose_sub", "unit": "unit", "project": "project_name"}[kind]
    return df[col] == name


def parse_target(target: str) -> tuple[str, str]:
    kind, _, name = target.partition(":")
    if kind not in ("sub", "unit", "project") or not name:
        raise ValueError(t("match.err_target"))
    return kind, name


def target_info(df: pd.DataFrame, kind: str, name: str) -> dict:
    rows = df[_mask(df, kind, name)]
    if rows.empty:
        raise InsufficientData(t("match.no_records", name=i18n.target_label(kind, name)))
    pick = lambda c: rows[c].dropna().mode().iloc[0] if rows[c].notna().any() else None
    info = {"kind": kind, "name": name, "sub": pick("purpose_sub"), "unit": pick("unit"), "college": pick("college")}
    if kind == "sub":
        info["sub"], info["unit"], info["college"] = name, None, None
    if kind == "unit":
        info["unit"] = name
        info["college"] = org.DEPT_TO_COLLEGE.get(name, info["college"])
    return info


def score_frame(df: pd.DataFrame, kind: str, name: str, as_of: int, info: dict | None = None) -> pd.DataFrame:
    """Score every donor with history up to `as_of`."""
    info = info or target_info(df, kind, name)
    h = df[(df["year"] <= as_of) & df["donor_code"].notna()].copy()
    w = 0.5 ** (as_of - h["year"])
    key = h["donor_code"]
    sat = lambda s: 1 - np.exp(-s)
    tm = _mask(h, kind, name)
    direct = sat((w * tm).groupby(key).sum())
    unit = pd.Series(0.0, index=direct.index)
    if info["unit"]:
        unit = sat((w * (h["unit"] == info["unit"])).groupby(key).sum())
        dept = h.groupby("donor_code")["dept"].first()
        unit = np.maximum(unit, (dept == info["unit"]).reindex(unit.index).fillna(False).astype(float))
    college = sat((w * (h["college"] == info["college"])).groupby(key).sum()) if info["college"] else pd.Series(0.0, index=direct.index)
    sub = sat((w * (h["purpose_sub"] == info["sub"])).groupby(key).sum()) if info["sub"] else pd.Series(0.0, index=direct.index)
    n_years = max(1, len([y for y in years_of(h)]))
    active = h.groupby("donor_code")["year"].nunique() / n_years
    tot = cash(h).groupby("donor_code")["amount_ntd"].sum().reindex(direct.index).fillna(0.0)
    capacity = np.log1p(tot) / max(np.log1p(tot).max(), 1)
    S = pd.DataFrame({"direct": direct, "unit": unit, "college": college, "sub": sub, "active": active, "capacity": capacity})
    S["score"] = sum(S[k] * WEIGHTS[k] for k in WEIGHTS) / MAX_SCORE * 100
    return S


def _evidence(df, donor, kind, name, info, as_of, S_row) -> list[str]:
    h = df[(df["donor_code"] == donor) & (df["year"] <= as_of)]
    ev: list[tuple[float, str]] = []
    th = h[_mask(h, kind, name)]
    if len(th):
        last = th.sort_values("year").iloc[-1]
        has_amt = pd.notna(last["amount_ntd"])
        what = i18n.target_label(kind, name)
        key = "match.gave_to_project" if kind == "project" else "match.gave_to_target"
        ev.append((S_row["direct"] * WEIGHTS["direct"],
                   t(key + ("_amt" if has_amt else ""), name=what, year=int(last["year"]), amount=last["amount_ntd"] if has_amt else 0)))
    dept = h["dept"].dropna()
    unit_txt = i18n.dept_label(info["unit"])
    if info["unit"] and len(dept) and dept.iloc[0] == info["unit"]:
        gy = h["grad_year"].dropna()
        ev.append((WEIGHTS["unit"], t("match.alumnus_cohort", unit=unit_txt, year=int(gy.iloc[0])) if len(gy)
                   else t("match.alumnus", unit=unit_txt)))
    elif info["unit"] and S_row["unit"] > 0 and not (kind == "unit" and len(th)):
        ev.append((S_row["unit"] * WEIGHTS["unit"], t("match.gave_to_unit_before", unit=unit_txt)))
    if info["college"] and S_row["college"] > 0:
        n = int((h["college"] == info["college"]).sum())
        ev.append((S_row["college"] * WEIGHTS["college"], t("match.college_gifts", n=n, college=i18n.college_label(info["college"]))))
    total_years = len(years_of(df[df["year"] <= as_of]))
    if info["sub"] and S_row["sub"] > 0 and kind != "sub":
        yrs = h[h["purpose_sub"] == info["sub"]]["year"].nunique()
        ev.append((S_row["sub"] * WEIGHTS["sub"], t("match.gave_to_sub_years", name=i18n.purpose_label(info["sub"]), k=yrs, n=total_years)))
    elif kind == "sub" and len(th):
        ev.append((S_row["sub"] * WEIGHTS["sub"], t("match.gave_to_sub_years", name=i18n.purpose_label(name), k=th["year"].nunique(), n=total_years)))
    ev.append((S_row["active"] * WEIGHTS["active"], t("match.active_years", k=h["year"].nunique(), n=total_years)))
    c = cash(h)
    if len(c):
        ev.append((S_row["capacity"] * WEIGHTS["capacity"], t("match.typical_gift", amount=c["amount_ntd"].median())))
    ev.sort(key=lambda x: -x[0])
    seen, out = set(), []
    for _, text in ev:
        if text not in seen:
            seen.add(text)
            out.append(text)
    return out[:4]


def list_targets(df: pd.DataFrame) -> list[dict]:
    out = []
    for s in org.PURPOSE_SUBS:
        n = df[df["purpose_sub"] == s]["donor_code"].nunique()
        if n:
            out.append({"id": f"sub:{s}", "kind": "purpose", "label": i18n.purpose_label(s), "donors": int(n)})
    for d, _, _ in org.DEPARTMENTS:
        n = df[df["unit"] == d]["donor_code"].nunique()
        if n:
            out.append({"id": f"unit:{d}", "kind": "department", "label": i18n.dept_label(d), "donors": int(n)})
    projects = df.dropna(subset=["project_name"]).groupby("project_name").agg(
        donors=("donor_code", "nunique"), first=("year", "min"), rows=("year", "size"))
    for name, r in projects.sort_values("donors", ascending=False).iterrows():
        if r["rows"] >= 3:
            out.append({"id": f"project:{name}", "kind": "project", "label": i18n.project_label(name), "donors": int(r["donors"]),
                        "first_year": int(r["first"])})
    return out


def rank(df: pd.DataFrame, target: str, top_n: int = 25, as_of: int | None = None) -> dict:
    kind, name = parse_target(target)
    ys = years_of(df)
    as_of = as_of or ys[-1]
    info = target_info(df, kind, name)
    S = score_frame(df, kind, name, as_of, info)
    S = S.sort_values("score", ascending=False)
    first = df.groupby("donor_code").agg(cls=("donor_class", "first"), anon=("anonymous", "max"))
    total = cash(df[df["year"] <= as_of]).groupby("donor_code")["amount_ntd"].sum()
    last_year = df[df["year"] <= as_of].groupby("donor_code")["year"].max()
    out = []
    for donor, r in S.head(top_n).iterrows():
        out.append({"donor_id": donor, "donor_class": first.loc[donor, "cls"],
                    "donor_class_label": i18n.class_label(first.loc[donor, "cls"]), "score": float(r["score"]),
                    "evidence": _evidence(df, donor, kind, name, info, as_of, r), "last_gift_year": int(last_year[donor]),
                    "total_given": float(total.get(donor, 0.0)), "anonymous": bool(first.loc[donor, "anon"]),
                    "components": {k: float(r[k] * WEIGHTS[k] / MAX_SCORE * 100) for k in WEIGHTS}})
    return {"target": target, "label": i18n.target_label(kind, name), "as_of_year": as_of, "n_candidates": int(len(S)), "candidates": out,
            "weights": WEIGHTS}


def evaluate(df: pd.DataFrame, ks=(20, 50), min_pos: int = 5, seed: int = 0) -> dict:
    ys = years_of(df)
    if len(ys) < 3:
        raise InsufficientData(t("match.eval_three_years"))
    last, hist = ys[-1], ys[-2]
    h = df[(df["year"] <= hist) & df["donor_code"].notna()]
    cands = sorted(h["donor_code"].unique())
    N = len(cands)
    rng = np.random.default_rng(seed)
    tie = pd.Series(rng.random(N), index=cands)
    activity = h.groupby("donor_code").size().reindex(cands).fillna(0)
    targets = [("sub", s) for s in org.PURPOSE_SUBS] + [("unit", d) for d, _, _ in org.DEPARTMENTS]
    rows = []
    for kind, name in targets:
        lastmask = (df["year"] == last) & _mask(df, kind, name)
        pos = set(df[lastmask]["donor_code"].dropna()) & set(cands)
        if len(pos) < min_pos:
            continue
        S = score_frame(df, kind, name, hist)
        S = S.reindex(cands).fillna(0.0)
        y = pd.Series([c in pos for c in cands], index=cands)
        prev = set(df[(df["year"] == hist) & _mask(df, kind, name)]["donor_code"].dropna()) & set(cands)
        row = {"target": i18n.target_label(kind, name), "positives": len(pos), "base_rate": len(pos) / N}
        order_model = S["score"].add(tie * 1e-6).sort_values(ascending=False).index
        order_pop = (activity + tie * 1e-6).sort_values(ascending=False).index
        s_prev, pos_in_prev = len(prev), len(prev & pos)
        for k in ks:
            row[f"model_p{k}"] = float(y[order_model[:k]].mean())
            row[f"popularity_p{k}"] = float(y[order_pop[:k]].mean())
            if s_prev >= k:
                row[f"lastyear_p{k}"] = pos_in_prev / s_prev
            else:
                rest = (len(pos) - pos_in_prev) / max(N - s_prev, 1)
                row[f"lastyear_p{k}"] = (pos_in_prev + (k - s_prev) * rest) / k
            row[f"random_p{k}"] = row["base_rate"]
        rows.append(row)
    if not rows:
        raise InsufficientData(t("match.eval_no_targets"))
    res = {"history_through": hist, "holdout_year": last, "n_candidates": N, "n_targets": len(rows), "by_k": []}
    boot_rng = np.random.default_rng(seed + 1)
    for k in ks:
        entry = {"k": k}
        for m in ("model", "lastyear", "popularity", "random"):
            vals = np.array([r[f"{m}_p{k}"] for r in rows])
            b = [vals[boot_rng.integers(0, len(vals), len(vals))].mean() for _ in range(500)]
            entry[m] = float(vals.mean())
            entry[f"{m}_ci_low"], entry[f"{m}_ci_high"] = float(np.percentile(b, 2.5)), float(np.percentile(b, 97.5))
        res["by_k"].append(entry)
    res["targets"] = [{"target": r["target"], "positives": r["positives"], "model_p20": r.get("model_p20"),
                       "lastyear_p20": r.get("lastyear_p20"), "random_p20": r["random_p20"]} for r in rows]
    res["notes"] = [t("match.note_cands"), t("match.note_new_projects")]
    return res


# ------------------------------------------------------------------------ free-text units (not only the preset department list)

_DROP = (
    "比較有可能", "可以找誰", "我現在要", "現在要", "有可能", "找誰",
    "募款", "捐款", "推薦", "名單", "給我", "教授", "老師",
    "我們是", "我是", "請問", "可以", "想要", "現在", "一個",
    "這個", "哪些", "背景", "相關", "查找", "科系", "想",
    "prospects", "prospect", "fundraising", "fundraise",
)
_UNIT_RE = re.compile(r"[\u4e00-\u9fffA-Za-z0-9]{2,40}(?:研究所|學系|學院|學程|中心)")
_SUFFIXES = ("研究所", "學系", "學院", "學程", "中心")


def _norm_name(s: str) -> str:
    t_ = unicodedata.normalize("NFKC", str(s or "")).lower()
    return re.sub(r"[\s　]+", "", t_)


def subject_phrase(text: str) -> str:
    """The unit or project named in a question, with the fundraising words taken off."""
    raw = unicodedata.normalize("NFKC", text or "")
    s = raw
    for w in _DROP:
        s = s.replace(w, " ")
    s = re.sub(r"[，。？！、,.?!\s　:：;；\"'「」『』()（）的]+", "", s)
    m = _UNIT_RE.search(s)
    if m:
        return m.group(0)
    return s.strip()


def _cores(s: str) -> list[str]:
    n = _norm_name(s)
    out = [n] if len(n) >= 2 else []
    for suf in _SUFFIXES:
        if n.endswith(suf) and len(n) - len(suf) >= 2:
            out.append(n[:-len(suf)])
    return out


def mentions(phrase: str, name) -> bool:
    """True when the two names refer to the same unit, allowing 研究所 / 學系 suffixes."""
    if phrase is None or name is None:
        return False
    try:
        if pd.isna(name):
            return False
    except (TypeError, ValueError):
        return False
    ps, ns = _cores(phrase), _cores(name)
    for p in ps:
        if len(p) < 2:
            continue
        for n in ns:
            if len(n) < 2:
                continue
            if p in n or (n in p and len(n) >= min(len(p), 4)):
                return True
    return False


def _blank(phrase: str) -> dict:
    return {"found": False, "phrase": phrase, "department": None, "target_id": None, "label": phrase,
            "projects": [], "donors": 0, "linked_ids": set(), "dept_values": []}


def _project_cards(rows: pd.DataFrame) -> list[dict]:
    cards = []

    def add(name: str, g: pd.DataFrame, translated: bool):
        purpose = str(g["purpose_sub"].dropna().mode().iloc[0]) if "purpose_sub" in g.columns and g["purpose_sub"].notna().any() else None
        unit = str(g["unit"].dropna().mode().iloc[0]) if "unit" in g.columns and g["unit"].notna().any() else None
        amount = float(cash(g)["amount_ntd"].sum()) if "amount_ntd" in g.columns and len(g) else 0.0
        cards.append({"name": name, "label": i18n.project_label(name) if translated else name,
                      "purpose": purpose, "purpose_label": i18n.purpose_label(purpose) if purpose else "",
                      "donors": int(g["donor_code"].nunique()) if "donor_code" in g.columns else 0,
                      "amount": amount, "unit": unit})

    if rows.empty:
        return cards
    rest = rows
    if "project_name" in rows.columns:
        named = rows[rows["project_name"].notna()]
        for name, g in named.groupby("project_name"):
            add(str(name), g, True)
        rest = rows[rows["project_name"].isna()]
    if "project_raw" in rest.columns:
        raw = rest[rest["project_raw"].notna()]
        for name, g in raw.groupby("project_raw"):
            add(str(name), g, False)
    return cards


def related_background(df: pd.DataFrame, text: str) -> dict:
    """Projects, units and donor backgrounds in the records that match this wording.

    A name that is not in the preset department list still matches when it appears on a project, a unit or a donor's department.
    """
    raw = unicodedata.normalize("NFKC", text or "").strip()
    phrase = subject_phrase(raw)
    display = phrase if len(phrase) >= 2 else raw
    if df is None or df.empty or "donor_code" not in df.columns:
        return _blank(display or raw)
    dept = org.find_department(raw) or (org.find_department(phrase) if phrase else None)
    hit = pd.Series(False, index=df.index)
    if dept is not None and "unit" in df.columns:
        hit = hit | (df["unit"] == dept[0])
    if dept is not None and "dept" in df.columns:
        hit = hit | (df["dept"] == dept[0])
    if len(phrase) >= 2:
        for col in ("project_name", "project_raw", "unit", "dept"):
            if col not in df.columns:
                continue
            hit = hit | df[col].map(lambda v, p=phrase: mentions(p, v))
        if "project_name" in df.columns:
            hit = hit | df["project_name"].map(lambda v, p=phrase: mentions(p, i18n.project_label(str(v))) if pd.notna(v) else False)
        for col in ("unit", "dept"):
            if col in df.columns:
                hit = hit | df[col].map(lambda v, p=phrase: mentions(p, i18n.dept_label(str(v))) if pd.notna(v) else False)
    rows = df[hit]
    if rows.empty:
        return _blank(display)
    projects = _project_cards(rows)
    units = [str(u) for u in rows["unit"].dropna().unique()] if "unit" in rows.columns else []
    target_id, label = None, display
    if dept and "unit" in df.columns and (df["unit"] == dept[0]).any():
        target_id, label = f"unit:{dept[0]}", i18n.dept_label(dept[0])
    elif len(units) == 1:
        target_id, label = f"unit:{units[0]}", i18n.dept_label(units[0])
    else:
        names = [str(n) for n in rows["project_name"].dropna().unique()] if "project_name" in rows.columns else []
        if len(names) == 1:
            target_id, label = f"project:{names[0]}", i18n.project_label(names[0])
        elif len(units) > 1:
            best = max(units, key=lambda u: int(rows.loc[rows["unit"] == u, "donor_code"].nunique()))
            target_id, label = f"unit:{best}", i18n.dept_label(best)
    dept_values = []
    if "dept" in rows.columns:
        for v in rows["dept"].dropna().unique():
            if (dept and str(v) == dept[0]) or mentions(phrase, v) or mentions(phrase, i18n.dept_label(str(v))):
                dept_values.append(str(v))
    return {"found": True, "phrase": display, "department": dept[0] if dept else None, "target_id": target_id,
            "label": label, "projects": projects, "donors": int(rows["donor_code"].nunique()),
            "linked_ids": set(rows["donor_code"].dropna().unique()), "dept_values": dept_values}


def _simple_linked(df: pd.DataFrame, linked: set, top_n: int) -> list[dict]:
    """Rank only the people already tied to this wording, when there is no single catalogue target."""
    h = df[df["donor_code"].isin(linked)].copy()
    if h.empty:
        return []
    first = h.groupby("donor_code").agg(cls=("donor_class", "first"), anon=("anonymous", "max"), last=("year", "max"))
    total = cash(h).groupby("donor_code")["amount_ntd"].sum()
    gave = set()
    if "project_name" in h.columns:
        gave |= set(h.loc[h["project_name"].notna(), "donor_code"])
    if "project_raw" in h.columns:
        gave |= set(h.loc[h["project_raw"].notna(), "donor_code"])
    mx = float(total.max()) if len(total) else 0.0
    out = []
    for donor, r in first.iterrows():
        amt = float(total.get(donor, 0.0))
        score = (70.0 + 30.0 * (amt / mx)) if donor in gave and mx else (55.0 if donor in gave else 40.0)
        ev: list[str] = []
        g = h[h["donor_code"] == donor]
        named = g.dropna(subset=["project_name"]) if "project_name" in g.columns else g.iloc[0:0]
        if len(named):
            last = named.sort_values("year").iloc[-1]
            has_amt = pd.notna(last["amount_ntd"])
            ev.append(t("match.gave_to_project" + ("_amt" if has_amt else ""), year=int(last["year"]),
                       amount=last["amount_ntd"] if has_amt else 0))
        dept = g["dept"].dropna() if "dept" in g.columns else []
        if len(dept):
            ev.append(t("match.alumnus", unit=i18n.dept_label(str(dept.iloc[0]))))
        out.append({"donor_id": donor, "donor_class": r["cls"], "donor_class_label": i18n.class_label(r["cls"]),
                    "score": float(score), "evidence": ev[:4], "last_gift_year": int(r["last"]) if pd.notna(r["last"]) else None,
                    "total_given": amt, "anonymous": bool(r["anon"])})
    out.sort(key=lambda d: -d["score"])
    return out[:top_n]


def _note_department(df: pd.DataFrame, cands: list[dict], dept_values: list[str], phrase: str) -> None:
    if not cands or not dept_values or "dept" not in df.columns:
        return
    wanted = set(dept_values)
    for d in cands:
        g = df[df["donor_code"] == d["donor_id"]]
        hit = next((str(v) for v in g["dept"].dropna().unique() if str(v) in wanted or mentions(phrase, v)), None)
        if not hit:
            continue
        line = t("match.alumnus", unit=i18n.dept_label(hit))
        if line not in d.get("evidence", []):
            d["evidence"] = [line, *d.get("evidence", [])][:4]


def _public_candidates(df: pd.DataFrame, depts: list[str], edu_names: list[str], top_n: int) -> tuple[list[dict], str | None]:
    """People who gave to a related department or an education-themed project. Department gifts come first."""
    linked: set = set()
    dept_ids: set = set()
    for dept in depts:
        ids = set(df.loc[df["unit"] == dept, "donor_code"].dropna())
        dept_ids |= ids
        linked |= ids
    if edu_names:
        linked |= set(df.loc[df["project_name"].isin(edu_names), "donor_code"].dropna())
    if not linked:
        return [], None
    pool: list[dict] = []
    target_id = f"unit:{depts[0]}" if depts else None
    if target_id:
        try:
            ranked = rank(df, target_id, max(int(df["donor_code"].nunique()), top_n))
            pool = [c for c in ranked["candidates"] if c["donor_id"] in linked]
        except (InsufficientData, ValueError, KeyError):
            pool = []
    if not pool:
        pool = _simple_linked(df, linked, max(top_n, len(linked)))
    dept_cands = sorted((c for c in pool if c["donor_id"] in dept_ids), key=lambda c: -c["score"])
    edu_only = sorted((c for c in pool if c["donor_id"] not in dept_ids), key=lambda c: -c["score"])
    reserve = min(3, len(edu_only)) if dept_cands and edu_only else 0
    chosen = dept_cands[:max(top_n - reserve, 0)] + edu_only[:reserve or top_n]
    seen = {c["donor_id"] for c in chosen}
    for c in dept_cands + edu_only:
        if len(chosen) >= top_n:
            break
        if c["donor_id"] not in seen:
            chosen.append(c)
            seen.add(c["donor_id"])
    return chosen[:top_n], target_id


def _from_public(df: pd.DataFrame, bg: dict, info: dict, top_n: int) -> dict | None:
    """The name is not in the ledger. Use the public description to rank nearby gifts."""
    from .public_unit import describe
    if not info.get("ok"):
        return None
    related = describe(info)
    if not related:
        return None
    depts = [d for d in info.get("departments") or [] if "unit" in df.columns and (df["unit"] == d).any()]
    edu_names: list[str] = []
    if info.get("education") and "project_name" in df.columns:
        for name in df["project_name"].dropna().unique():
            label = f"{name} {i18n.project_label(str(name))}".lower()
            if any(k in label for k in ("教育", "通識", "數位學習", "學習科技", "general education")):
                edu_names.append(str(name))
    base = {**bg, "via": "public", "public_related": related, "public_source": info.get("source") or ""}
    if not depts and not edu_names:
        return {**base, "found": False, "candidates": [], "n_candidates": 0}
    cands, target_id = _public_candidates(df, depts, edu_names, top_n)
    if not cands:
        return {**base, "found": False, "candidates": [], "n_candidates": 0}
    mask = pd.Series(False, index=df.index)
    if depts and "unit" in df.columns:
        mask = mask | df["unit"].isin(depts)
    if edu_names and "project_name" in df.columns:
        mask = mask | df["project_name"].isin(edu_names)
    rows = df[mask]
    projects = _project_cards(rows)
    label = i18n.dept_label(depts[0]) if depts else related
    return {**base, "found": True, "department": depts[0] if depts else None, "target_id": target_id,
            "label": label, "projects": projects, "donors": int(rows["donor_code"].nunique()) if len(rows) else len(cands),
            "linked_ids": {c["donor_id"] for c in cands}, "dept_values": depts, "candidates": cands, "n_candidates": len(cands)}


def prospects_for_text(df: pd.DataFrame, text: str, top_n: int = 10) -> dict:
    """Look up a unit in the records, then rank people tied to what was found.

    When the records never use that name, a public page is read first so a related department
    (for example 資訊工程) and an education theme can still produce a list.
    """
    bg = related_background(df, text)
    if not bg["found"]:
        from .public_unit import public_background
        widened = _from_public(df, bg, public_background(bg["phrase"]), top_n)
        if widened:
            return widened
        return {**bg, "candidates": [], "n_candidates": 0}
    linked = set(bg["linked_ids"])
    wide = bool(bg["department"])
    cands: list[dict] = []
    n_scored = len(linked)
    label = bg["label"]
    if bg["target_id"]:
        try:
            universe = max(int(df["donor_code"].nunique()), top_n)
            ranked = rank(df, bg["target_id"], universe)
            label = ranked["label"] or label
            pool = ranked["candidates"]
            if wide:
                cands = sorted(pool, key=lambda d: (d["donor_id"] not in linked, -d["score"]))[:top_n]
                n_scored = ranked["n_candidates"]
            else:
                cands = sorted((d for d in pool if d["donor_id"] in linked), key=lambda d: -d["score"])[:top_n]
                n_scored = len(linked)
        except (InsufficientData, ValueError, KeyError):
            cands = []
    if not cands and linked:
        cands = _simple_linked(df, linked, top_n)
        n_scored = len(linked)
        label = label or bg["phrase"]
    _note_department(df, cands, bg["dept_values"], bg["phrase"])
    return {**bg, "label": label, "candidates": cands, "n_candidates": n_scored}
