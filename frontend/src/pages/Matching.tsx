import { useMemo, useState } from "react";
import { useMatchEval, useRank, useTargets } from "../api/hooks";
import { Card, Notice, PageHeader, Q } from "../components/ui";
import { useApp } from "../context/AppContext";
import { useI18n } from "../i18n";
import type { Key } from "../i18n/en";
import { PALETTE } from "../lib/chart";

export default function Matching() {
  const { datasetId, dataset } = useApp();
  const { t, fmt } = useI18n();
  const targets = useTargets(datasetId);
  const [target, setTarget] = useState<string | undefined>();
  const chosen = target ?? targets.data?.find((x) => x.kind === "purpose")?.id;
  const rank = useRank(datasetId, chosen);
  const ev = useMatchEval(datasetId);
  const groups = useMemo(() => {
    const list = targets.data ?? [];
    const latest = Math.max(0, ...list.map((x) => x.first_year ?? 0));
    return [
      { label: t("match.group_purpose"), items: list.filter((x) => x.kind === "purpose") },
      { label: t("match.group_dept"), items: list.filter((x) => x.kind === "department") },
      { label: t("match.group_new", { year: latest }), items: list.filter((x) => x.kind === "project" && x.first_year === latest) },
      { label: t("match.group_other"), items: list.filter((x) => x.kind === "project" && x.first_year !== latest) },
    ].filter((g) => g.items.length);
  }, [targets.data, t]);

  return (
    <>
      <PageHeader title={t("match.title")} question={t("q.match")} desc={t("match.desc")}>
        <label className="field wide">{t("match.match_to")}
          <select value={chosen ?? ""} onChange={(e) => setTarget(e.target.value)}>
            {groups.map((g) => (
              <optgroup key={g.label} label={g.label}>
                {g.items.map((x) => <option key={x.id} value={x.id}>{t("match.option", { label: x.label, n: x.donors })}</option>)}
              </optgroup>
            ))}
          </select>
        </label>
      </PageHeader>
      <Q q={targets}>{() => (
        <div className="grid g-main">
          <Card icon="match" title={t("match.best", { label: rank.data?.label ?? "…" })} sub={rank.data ? t("match.best_sub", { n: rank.data.n_candidates }) : undefined}>
            <Q q={rank}>{(r) => (
              <>
                {r.candidates.map((c, i) => (
                  <div className="cand" key={c.donor_id}>
                    <div className="score"><b className="num">{c.score.toFixed(0)}</b><span className="small muted">#{i + 1}</span></div>
                    <div>
                      <div><b className="mono">{c.donor_id}</b> <span className="muted small">{t("match.cand_meta", { cls: c.donor_class_label, anon: c.anonymous ? ` · ${t("kind.anonymous")}` : "", year: c.last_gift_year, total: fmt.ntd(c.total_given) })}</span></div>
                      <div className="stackbar" role="img" aria-label={Object.entries(c.components).map(([k, v]) => `${t(`signal.${k}` as Key)} ${v.toFixed(0)}`).join(", ")}>
                        {Object.entries(c.components).map(([k, v], si) => <i key={k} title={`${t(`signal.${k}` as Key)}: ${v.toFixed(0)}`} style={{ width: `${Math.max(v, 0)}%`, background: PALETTE[si % PALETTE.length] }} />)}
                      </div>
                      <ul className="evidence">{c.evidence.map((e) => <li key={e}>{e}</li>)}</ul>
                    </div>
                  </div>
                ))}
                <div className="legend-note" style={{ display: "flex", flexWrap: "wrap", gap: "4px 14px" }}>
                  <b>{t("match.signals")}:</b>
                  {Object.keys(r.weights).map((k, si) => <span key={k}><i style={{ display: "inline-block", width: 10, height: 10, borderRadius: 3, background: PALETTE[si % PALETTE.length], marginRight: 5 }} />{t(`signal.${k}` as Key)} {r.weights[k]}</span>)}
                </div>
                <div className="how">{t("how.match")}</div>
              </>
            )}</Q>
          </Card>
          <Card icon="shield" title={t("match.eval_title")} sub={t("match.eval_sub")}>
            <Q q={ev}>{(e) => (
              <>
                <div className="scroll"><table className="t">
                  <thead><tr><th>{t("match.th_method")}</th>{e.by_k.map((k) => <th className="r" key={k.k}>{t("match.th_precision", { k: k.k })}</th>)}</tr></thead>
                  <tbody>
                    {([["model", "match.m_model"], ["lastyear", "match.m_lastyear"], ["popularity", "match.m_popularity"], ["random", "match.m_random"]] as const).map(([key, label]) => (
                      <tr key={key} className={key === "model" ? "best" : ""}>
                        <td><b>{t(label)}</b></td>
                        {e.by_k.map((k) => <td className="r num" key={k.k}>{fmt.pct(k[key], 1)} <span className="muted small">({fmt.pct(k[`${key}_ci_low` as const], 0)}–{fmt.pct(k[`${key}_ci_high` as const], 0)})</span></td>)}
                      </tr>
                    ))}
                  </tbody></table></div>
                <div className="legend-note">{t("match.eval_note", { targets: e.n_targets, candidates: e.n_candidates })}</div>
                {dataset?.is_mock && <Notice tone="warn" title={t("match.mock_title")}>{t("match.mock_text")}</Notice>}
                <ul className="small muted" style={{ paddingLeft: 18 }}>{e.notes.map((n) => <li key={n}>{n}</li>)}</ul>
              </>
            )}</Q>
          </Card>
        </div>
      )}</Q>
    </>
  );
}
