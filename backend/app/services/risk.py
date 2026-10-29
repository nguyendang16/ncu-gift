"""WP4 (part 2): lapse risk, ranked by expected value at risk.

Backtest: train on the earliest year-to-year transition, test on the latest one
(the model never sees the test labels). The model used for scoring is then
retrained on every available transition and applied to the latest year's donors.
Mega-gifts are capped when ranking by value at risk (config.RISK_VALUE_CAP);
principal-tier prospects are handled individually, not statistically.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.preprocessing import StandardScaler

from .. import config, i18n, org
from ..i18n import t
from .frame import InsufficientData, active_sets, cash, wilson, years_of

FEATURES = ["log_total", "n_gifts", "log_max_gift", "recurring", "anonymous", "class_alumni", "class_friends",
            "class_company", "class_org", "last_month", "n_projects", "card", "wire", "tenure"]
CLASS_FEATURE = {"class_alumni": "alumni", "class_friends": "friends", "class_company": "company", "class_org": "organisation"}


def donor_features(df: pd.DataFrame, year: int, A: dict, ys: list[int]) -> pd.DataFrame:
    cur = df[(df["year"] == year) & df["donor_code"].notna()]
    g = cur.groupby("donor_code")
    idx = g.size().index
    amt = cash(cur).groupby("donor_code")["amount_ntd"]
    f = pd.DataFrame(index=idx)
    f["total"] = amt.sum().reindex(idx).fillna(0.0)
    f["max_gift"] = amt.max().reindex(idx).fillna(0.0)
    f["log_total"] = np.log1p(f["total"])
    f["log_max_gift"] = np.log1p(f["max_gift"])
    f["n_gifts"] = g.size().astype(float)
    f["recurring"] = g["mode"].apply(lambda s: float((s == "recurring").any()))
    f["anonymous"] = g["anonymous"].max().astype(float)
    cls = g["donor_class"].first()
    for name, c in CLASS_FEATURE.items():
        f[name] = (cls == c).astype(float)
    f["last_month"] = g["date"].max().dt.month.fillna(6).astype(float)
    f["n_projects"] = g["project_name"].nunique().astype(float)
    f["card"] = g["method"].apply(lambda s: float((s == "credit_card").any()))
    f["wire"] = g["method"].apply(lambda s: float((s == "bank_transfer").any()))
    f["tenure"] = [float(sum(1 for y in ys if y <= year and d in A.get(y, set()))) for d in idx]
    f["donor_class"] = cls
    return f


def _xy(df, a, b, A, ys):
    X = donor_features(df, a, A, ys)
    y = np.array([0 if d in A.get(b, set()) else 1 for d in X.index])
    return X, y


def _fit(X: pd.DataFrame, y: np.ndarray):
    sc = StandardScaler().fit(X[FEATURES])
    lr = LogisticRegression(max_iter=2000).fit(sc.transform(X[FEATURES]), y)
    return sc, lr


def _phrase(feature: str, row: pd.Series, z: float) -> str | None:
    """Reason text depends on the donor's actual value (z = standardised value), not on the coefficient's
    sign: total giving and largest gift are strongly correlated, so their coefficients can flip."""
    if feature == "tenure":
        return t("risk.reason_short_history", n=int(row["tenure"])) if z < 0 else None
    if feature == "log_total":
        return t("risk.reason_low_total" if z < 0 else "risk.reason_large_oneoff", amount=row["total"])
    if feature == "log_max_gift":
        return t("risk.reason_big_gift" if z > 0 else "risk.reason_small_gifts", amount=row["max_gift"])
    if feature == "recurring":
        return t("risk.reason_no_recurring") if row["recurring"] == 0 else None
    if feature == "anonymous":
        return t("risk.reason_anonymous") if row["anonymous"] == 1 else None
    if feature in CLASS_FEATURE:
        return t("risk.reason_class", cls=i18n.class_label(CLASS_FEATURE[feature])) if row[feature] == 1 else None
    if feature == "n_gifts":
        return t("risk.reason_once") if row["n_gifts"] == 1 else None
    if feature == "n_projects":
        return t("risk.reason_single_project") if row["n_projects"] == 1 else None
    if feature == "last_month":
        return t("risk.reason_early", m=int(row["last_month"])) if row["last_month"] <= 6 else None
    return None


def risk_report(df: pd.DataFrame, ks=(20, 50, 100), cap: float = config.RISK_VALUE_CAP, top_n: int = 50,
                seed: int = 0) -> dict:
    ys = years_of(df)
    if len(ys) < 2:
        raise InsufficientData(t("risk.one_year"))
    A = active_sets(df)
    pairs = [(ys[i], ys[i + 1]) for i in range(len(ys) - 1)]
    notes, metrics = [], None

    if len(pairs) >= 2:
        Xtr, ytr = _xy(df, *pairs[0], A, ys)
        Xte, yte = _xy(df, *pairs[-1], A, ys)
        sc, lr = _fit(Xtr, ytr)
        p = lr.predict_proba(sc.transform(Xte[FEATURES]))[:, 1]
        auc = float(roc_auc_score(yte, p))
        rng = np.random.default_rng(seed)
        boots = []
        for _ in range(300):
            i = rng.integers(0, len(yte), len(yte))
            if len(set(yte[i])) == 2:
                boots.append(roc_auc_score(yte[i], p[i]))
        val = np.minimum(Xte["total"].to_numpy(), cap)
        order = np.argsort(-(p * val))
        # simple rules anyone could apply without a model: donors who gave once (smallest gift first), and the biggest donors
        once = np.argsort(-((Xte["n_gifts"].to_numpy() == 1).astype(float) - 1e-9 * Xte["total"].to_numpy()), kind="stable")
        biggest = np.argsort(-val, kind="stable")
        prec = []
        for k in ks:
            if k > len(yte):
                continue
            top = order[:k]
            hits = int(yte[top].sum())
            lo, hi = wilson(hits, k)
            prec.append({"k": k, "hits": hits, "precision": hits / k, "ci_low": lo, "ci_high": hi,
                         "rule_once_precision": float(yte[once[:k]].mean()),
                         "value_captured": float((val[top] * yte[top]).sum()),
                         "value_captured_biggest": float((val[biggest[:k]] * yte[biggest[:k]]).sum())})
        metrics = {"auc": auc, "auc_ci_low": float(np.percentile(boots, 2.5)), "auc_ci_high": float(np.percentile(boots, 97.5)),
                   "train": f"{pairs[0][0]}→{pairs[0][1]}", "test": f"{pairs[-1][0]}→{pairs[-1][1]}",
                   "n_train": int(len(ytr)), "n_test": int(len(yte)),
                   "lapse_rate_train": float(ytr.mean()), "lapse_rate_test": float(yte.mean()), "precision_at_k": prec}
        notes.append(t("risk.note_lift"))
    else:
        notes.append(t("risk.note_insample"))

    parts = [_xy(df, a, b, A, ys) for a, b in pairs]
    Xall = pd.concat([x for x, _ in parts])
    yall = np.concatenate([y for _, y in parts])
    sc, lr = _fit(Xall, yall)

    last = ys[-1]
    S = donor_features(df, last, A, ys)
    Z = sc.transform(S[FEATURES])
    p = lr.predict_proba(Z)[:, 1]
    contrib = Z * lr.coef_[0]
    S["p_lapse"] = p
    S["value"] = np.minimum(S["total"], cap)
    S["var"] = S["p_lapse"] * S["value"]
    anon = df[df["year"] == last].groupby("donor_code")["anonymous"].max()
    donors = []
    for pos in np.argsort(-S["var"].to_numpy())[:top_n]:
        row = S.iloc[pos]
        reasons = []
        for j in np.argsort(-contrib[pos]):
            if contrib[pos][j] <= 0:
                break
            ph = _phrase(FEATURES[j], row, float(Z[pos][j]))
            if ph:
                reasons.append(ph)
            if len(reasons) == 3:
                break
        donors.append({"donor_id": S.index[pos], "donor_class": row["donor_class"],
                       "donor_class_label": i18n.class_label(row["donor_class"]), "p_lapse": float(row["p_lapse"]),
                       "giving_last_year": float(row["total"]), "value_at_risk": float(row["var"]),
                       "anonymous": bool(anon.get(S.index[pos], False)), "tenure": int(row["tenure"]),
                       "capped": bool(row["total"] > cap), "reasons": reasons})
    order = np.argsort(-S["var"].to_numpy())
    points = [{"donor_id": S.index[i], "donor_class": S.iloc[i]["donor_class"], "donor_class_label": i18n.class_label(S.iloc[i]["donor_class"]),
               "giving_last_year": float(S.iloc[i]["total"]), "p_lapse": float(S.iloc[i]["p_lapse"]),
               "value_at_risk": float(S.iloc[i]["var"]), "capped": bool(S.iloc[i]["total"] > cap)}
              for i in order[:300] if S.iloc[i]["total"] > 0]
    coefs = [{"feature": t(f"risk.feat.{f}"), "coef": float(c)} for f, c in zip(FEATURES, lr.coef_[0])]
    coefs.sort(key=lambda x: -abs(x["coef"]))
    notes.append(t("risk.note_cap", cap=cap))
    return {"scoring_year": last, "next_year": last + 1, "metrics": metrics, "coefficients": coefs,
            "donors": donors, "points": points, "n_scored": int(len(S)), "notes": notes}
