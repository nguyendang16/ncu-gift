"""Backtest of the lapse-risk list on a copy of the real data. Prints aggregates only (no donor names or codes).

Protocol (fixed before looking at results): train on the earlier transition, test on the latest one, the same split the app uses.
The list is the top k donors by expected value at risk. Compared against picking k donors at random and against simple rules
anyone could apply without a model. 95% intervals by bootstrap over test donors. Label-shuffle check: with the outcome shuffled,
lift must fall to about 1 (otherwise something leaks).

  python -m scripts.backtest_risk --db /path/to/copy.db --dataset 2
"""
from __future__ import annotations

import argparse

import numpy as np
from sklearn.metrics import roc_auc_score
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app import config
from app.services import risk as rk
from app.services.frame import active_sets, load_df, years_of

KS = (20, 50, 100)


def lift_at(score: np.ndarray, y: np.ndarray, val: np.ndarray, k: int):
    top = np.argsort(-score, kind="stable")[:k]
    prec = y[top].mean()
    cap = (val[top] * y[top]).sum()
    exp = k / len(y) * (val * y).sum()
    return prec / y.mean() if y.mean() else np.nan, cap / exp if exp else np.nan, int(y[top].sum())


def boot(score, y, val, k, rng, n=500):
    out_c, out_v = [], []
    for _ in range(n):
        i = rng.integers(0, len(y), len(y))
        if y[i].mean() == 0:
            continue
        c, v, _h = lift_at(score[i], y[i], val[i], k)
        out_c.append(c); out_v.append(v)
    return np.percentile(out_c, [2.5, 97.5]), np.percentile(out_v, [2.5, 97.5])


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--db", required=True); ap.add_argument("--dataset", type=int, required=True)
    a = ap.parse_args()
    eng = create_engine(f"sqlite:///{a.db}")
    with Session(eng) as s:
        df = load_df(s, a.dataset)
    ys = years_of(df); A = active_sets(df)
    pairs = [(ys[i], ys[i + 1]) for i in range(len(ys) - 1)]
    print(f"years {ys}; donors with an id per year: " + ", ".join(f"{y}:{len(A[y])}" for y in ys))
    (a0, b0), (a1, b1) = pairs[0], pairs[-1]
    Xtr, ytr = rk._xy(df, a0, b0, A, ys); Xte, yte = rk._xy(df, a1, b1, A, ys)
    sc, lr = rk._fit(Xtr, ytr)
    p = lr.predict_proba(sc.transform(Xte[rk.FEATURES]))[:, 1]
    val = np.minimum(Xte["total"].to_numpy(), config.RISK_VALUE_CAP)
    print(f"train {a0}->{b0} n={len(ytr)} lapse={ytr.mean():.1%} | test {a1}->{b1} n={len(yte)} lapse={yte.mean():.1%}")
    rng = np.random.default_rng(0)

    scores = {
        "MODEL (p x value)": p * val,
        "model probability only": p,
        "rule: gave least": -Xte["total"].to_numpy(),
        "rule: gave once": (Xte["n_gifts"].to_numpy() == 1).astype(float) + 1e-9 * -Xte["total"].to_numpy(),
        "rule: no recurring, biggest gift": (1 - Xte["recurring"].to_numpy()) * val,
        "rule: biggest gift (no model)": val,
    }
    print("\nAUC (higher is better, 0.5 = chance):")
    for n, sco in scores.items():
        print(f"  {n:34s} {roc_auc_score(yte, sco):.3f}")
    print("\nTop-k lists. 'catch' = lift in number of real lapsers caught vs random; 'money' = lift in money at risk caught vs random")
    for k in KS:
        print(f"  k={k}")
        for n, sco in scores.items():
            c, v, h = lift_at(sco, yte, val, k)
            (cl, ch), (vl, vh) = boot(sco, yte, val, k, rng)
            print(f"    {n:34s} hits {h:3d}/{k}  catch {c:4.2f}x [{cl:4.2f}-{ch:4.2f}]  money {v:4.2f}x [{vl:4.2f}-{vh:4.2f}]")
    print("\nLabel-shuffle check (model, 200 shuffles, expect about 1.0x):")
    for k in KS:
        cs, vs = [], []
        for _ in range(200):
            yy = rng.permutation(yte)
            if yy.mean() == 0:
                continue
            c, v, _h = lift_at(p * val, yy, val, k); cs.append(c); vs.append(v)
        print(f"  k={k}  catch {np.mean(cs):.2f}x  money {np.mean(vs):.2f}x   AUC {np.mean([roc_auc_score(rng.permutation(yte), p) for _ in range(100)]):.3f}")


if __name__ == "__main__":
    main()
