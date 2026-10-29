import { useState } from "react";
import { useRisk } from "../api/hooks";
import { Chart } from "../components/Chart";
import { How, Bar, Card, Notice, PageHeader, Q } from "../components/ui";
import { useApp } from "../context/AppContext";
import { useI18n } from "../i18n";
import { bubbleOption } from "../lib/options";

export default function Risk() {
  const { datasetId } = useApp();
  const { t, fmt } = useI18n();
  const q = useRisk(datasetId);
  const [hideCapped, setHideCapped] = useState(false);
  return (
    <>
      <PageHeader title={t("risk.title")} question={t("q.risk")} desc={t("risk.desc")} />
      <Q q={q} label={t("ui.scoring")}>{(r) => {
        const m = r.metrics;
        const rows = r.donors.filter((d) => !(hideCapped && d.capped));
        return (
          <>
            {r.points.length > 0 && (
              <Card icon="risk" title={t("bubble.title")} sub={t("bubble.sub", { n: r.points.length })} help="tip.bubble">
                <Chart option={bubbleOption(r.points, fmt, t)} label={t("bubble.aria")} height={360} />
                <How>{t("how.bubble")}</How>
              </Card>
            )}
            <div className="grid g-main">
              <Card icon="shield" title={t("risk.how_title")} sub={m ? t("risk.how_sub", { train: m.train, test: m.test }) : t("risk.how_sub_none")}>
                {m ? (
                  <>
                    <div className="kpis k3" style={{ marginBottom: 12 }}>
                      <div className="kpi"><div className="l">{t("risk.auc")}</div><div className="v">{m.auc.toFixed(2)}</div><div className="s">{t("risk.auc_interval", { lo: m.auc_ci_low.toFixed(2), hi: m.auc_ci_high.toFixed(2) })}</div></div>
                      <div className="kpi"><div className="l">{t("risk.tested")}</div><div className="v">{m.n_test}</div><div className="s">{t("risk.tested_sub", { pct: fmt.pct(m.lapse_rate_test, 0) })}</div></div>
                      <div className="kpi"><div className="l">{t("risk.trained")}</div><div className="v">{m.n_train}</div><div className="s">{t("risk.trained_sub", { pct: fmt.pct(m.lapse_rate_train, 0) })}</div></div>
                    </div>
                    <div className="scroll"><table className="t">
                      <thead><tr><th>{t("risk.th_contacts")}</th><th className="r">{t("risk.th_hit")}</th><th className="r">{t("risk.th_all")}</th><th className="r">{t("risk.th_once")}</th><th className="r">{t("risk.th_flagged")}</th><th className="r">{t("risk.th_random")}</th></tr></thead>
                      <tbody>{m.precision_at_k.map((p) => (
                        <tr key={p.k}><td>{t("risk.top_k", { k: p.k })}</td><td className="r num">{p.hits} ({fmt.pct(p.precision, 0)}) <span className="muted">{fmt.pct(p.ci_low, 0)}–{fmt.pct(p.ci_high, 0)}</span></td><td className="r num">{fmt.pct(m.lapse_rate_test, 0)}</td><td className="r num">{fmt.pct(p.rule_once_precision, 0)}</td><td className="r num">{fmt.compact(p.value_captured)}</td><td className="r num">{fmt.compact(p.value_captured_biggest)}</td></tr>
                      ))}</tbody></table></div>
                  </>
                ) : <Notice tone="warn">{t("risk.insample_notice")}</Notice>}
              </Card>
              <Card icon="chart" title={t("risk.relies_title")} sub={t("risk.relies_sub")}>
                {r.coefficients.slice(0, 7).map((c) => (
                  <div key={c.feature} style={{ display: "grid", gridTemplateColumns: "1fr 90px 44px", gap: 8, alignItems: "center", fontSize: "0.85rem", marginBottom: 5 }}>
                    <span>{c.feature}</span><Bar value={Math.abs(c.coef)} max={1} amber={c.coef > 0} /><span className="num muted">{c.coef > 0 ? "+" : ""}{c.coef.toFixed(2)}</span>
                  </div>
                ))}
                <div className="legend-note">{t("risk.relies_note")}</div>
              </Card>
            </div>

            <Card icon="people" title={t("risk.list_title", { year: r.next_year })} sub={t("risk.list_sub", { n: r.n_scored, year: r.scoring_year })}
              right={<label className="small muted"><input type="checkbox" checked={hideCapped} onChange={(e) => setHideCapped(e.target.checked)} /> {t("risk.hide_capped")}</label>}>
              <div className="scroll"><table className="t">
                <thead><tr><th>#</th><th>{t("col.donor")}</th><th className="r">{t("col.years")}</th><th className="r">{t("risk.th_gave", { year: r.scoring_year })}</th><th>{t("risk.th_chance")}</th><th className="r">{t("risk.th_var")}</th><th>{t("risk.th_why")}</th></tr></thead>
                <tbody>{rows.map((d, i) => (
                  <tr key={d.donor_id}>
                    <td className="muted">{i + 1}</td>
                    <td><b className="mono">{d.donor_id}</b><div className="small muted">{d.donor_class_label}{d.anonymous && ` · ${t("kind.anonymous")}`}</div></td>
                    <td className="r num">{d.tenure}</td>
                    <td className="r num">{fmt.ntd(d.giving_last_year)}{d.capped && <div className="chip warn" title={t("risk.capped_title")}>{t("risk.capped")}</div>}</td>
                    <td style={{ minWidth: 130 }}><div style={{ display: "flex", gap: 8, alignItems: "center" }}><Bar value={d.p_lapse} amber /><span className="num small">{fmt.pct(d.p_lapse, 0)}</span></div></td>
                    <td className="r num"><b>{fmt.compact(d.value_at_risk)}</b></td>
                    <td>{d.reasons.length ? d.reasons.map((x) => <span className="chip" key={x}>{x}</span>) : <span className="muted small">{t("risk.no_factor")}</span>}</td>
                  </tr>
                ))}</tbody></table></div>
            </Card>
            <div style={{ height: 16 }} />
            <Notice tone="info"><ul style={{ margin: 0, paddingLeft: 18 }}>{r.notes.map((n) => <li key={n}>{n}</li>)}</ul></Notice>
          </>
        );
      }}</Q>
    </>
  );
}
