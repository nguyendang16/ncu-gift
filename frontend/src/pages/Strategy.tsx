import { useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useScenario } from "../api/hooks";
import { Chart } from "../components/Chart";
import { How, Card, Notice, PageHeader, Q, useDebounced } from "../components/ui";
import { useApp } from "../context/AppContext";
import { useI18n } from "../i18n";
import { fanOption } from "../lib/options";

function Slider({ label, value, min, max, step, onChange, text }: { label: string; value: number; min: number; max: number; step: number; onChange: (v: number) => void; text: string }) {
  const id = "sl-" + label.replace(/[^\w一-鿿]+/g, "-");
  return (
    <div className="slider">
      <div className="row"><label htmlFor={id}>{label}</label><b className="num">{text}</b></div>
      <input id={id} type="range" min={min} max={max} step={step} value={value} onChange={(e) => onChange(Number(e.target.value))} />
    </div>
  );
}

export default function Strategy() {
  const { datasetId, settings } = useApp();
  const { t, tx, fmt } = useI18n();
  // the AI analyst links here with its settings in the address, so the person can keep exploring from the same point
  const [qs] = useSearchParams();
  const num = (k: string, d: number) => { const v = Number(qs.get(k)); return qs.has(k) && Number.isFinite(v) ? v : d; };
  const [r1, setR1] = useState(num("r1", 0)), [r2, setR2] = useState(num("r2", 0)), [mult, setMult] = useState(num("mult", 1)), [rec, setRec] = useState(num("rec", 0)), [gift, setGift] = useState(num("gift", 0));
  const body = useDebounced({ dataset_id: datasetId, exceptional_threshold: settings.exceptional, r1_uplift_pp: r1, r2_uplift_pp: r2, new_donor_multiplier: mult, recurring_conversion_pct: rec, major_gift_ntd: gift }, 250);
  const q = useScenario(body);
  const reset = () => { setR1(0); setR2(0); setMult(1); setRec(0); setGift(0); };
  return (
    <>
      <PageHeader title={t("strategy.title")} question={t("q.strategy")} desc={t("strategy.desc")}>
        <button className="btn" onClick={reset}>{t("strategy.reset")}</button>
      </PageHeader>
      <Notice tone="warn" title={t("strategy.warn_title")}>{t("strategy.warn_text")}</Notice>
      <div className="grid g-side">
        <Card icon="strategy" title={t("strategy.levers")} sub={t("strategy.levers_sub")}>
          <Slider label={t("strategy.l_first")} value={r1} min={0} max={20} step={1} onChange={setR1} text={t("strategy.pp", { n: `+${r1}` })} />
          <Slider label={t("strategy.l_repeat")} value={r2} min={0} max={10} step={1} onChange={setR2} text={t("strategy.pp", { n: `+${r2}` })} />
          <Slider label={t("strategy.l_inflow")} value={mult} min={0.5} max={1.5} step={0.05} onChange={setMult} text={`× ${mult.toFixed(2)}`} />
          <Slider label={t("strategy.l_recurring")} value={rec} min={0} max={30} step={1} onChange={setRec} text={`${rec}%`} />
          <div className="field"><label htmlFor="gift">{t("strategy.l_gift")}</label>
            <select id="gift" className="inline" value={gift} onChange={(e) => setGift(Number(e.target.value))}>
              {[0, 5e6, 2e7, 5e7].map((v) => <option key={v} value={v}>{v ? fmt.ntd(v) : t("strategy.none")}</option>)}
            </select></div>
        </Card>
        <div>
          <Q q={q}>{(s) => (
            <>
              <Card icon="trend" title={t("strategy.result_title", { year: s.projection_year })} sub={t("strategy.result_sub", { threshold: fmt.compact(s.exceptional_threshold), base: s.base_year })}>
                <div className="kpis k3" style={{ marginBottom: 8 }}>
                  <div className="kpi"><div className="l">{t("strategy.baseline")}</div><div className="v">{fmt.compact(s.baseline.expected)}</div><div className="s">{fmt.compact(s.baseline.low)} – {fmt.compact(s.baseline.high)}</div></div>
                  <div className="kpi accent"><div className="l">{t("strategy.scenario")}</div><div className="v">{fmt.compact(s.scenario.expected)}</div><div className="s">{fmt.compact(s.scenario.low)} – {fmt.compact(s.scenario.high)}</div></div>
                  <div className="kpi"><div className="l">{t("strategy.difference")}</div><div className={`v delta ${s.scenario.delta_vs_baseline >= 0 ? "up" : "down"}`}>{s.scenario.delta_vs_baseline >= 0 ? "+" : "−"}{fmt.compact(Math.abs(s.scenario.delta_vs_baseline))}</div><div className="s">{t("strategy.vs_baseline")}</div></div>
                </div>
                <Chart option={fanOption(s, fmt, t)} height={300} label={t("strategy.range_aria")} />
                <How>{t("how.fan")}</How>
                {s.exceptional_line.entered_gift > 0 && <Notice tone="info">{tx("strategy.exc_arrives", { gift: fmt.ntd(s.exceptional_line.entered_gift), total: fmt.compact(s.exceptional_line.total_if_gift_arrives), note: s.exceptional_line.note })}</Notice>}
              </Card>
              <div style={{ height: 16 }} />
              <Card icon="data" title={t("strategy.built_title")}>
                <div className="scroll"><table className="t">
                  <thead><tr><th>{t("strategy.th_cohort")}</th><th className="r">{t("strategy.th_donors")}</th><th className="r">{t("strategy.th_chance")}</th><th className="r">{t("strategy.th_typical")}</th><th className="r">{t("strategy.th_expected")}</th></tr></thead>
                  <tbody>{s.cohorts.map((c) => (
                    <tr key={c.cohort}><td>{c.cohort}</td><td className="r num">{c.donors}</td>
                      <td className="r num">{c.retention_scenario == null ? "–" : fmt.pct(c.retention_scenario, 0)}{c.retention_base != null && c.retention_scenario !== c.retention_base && <span className="muted small"> {t("strategy.was", { pct: fmt.pct(c.retention_base, 0) })}</span>}</td>
                      <td className="r num">{fmt.ntd(c.avg_gift)}</td><td className="r num">{fmt.compact(c.expected_scenario)}</td></tr>
                  ))}</tbody></table></div>
                <h3 style={{ margin: "14px 0 6px" }}>{t("strategy.observed_title")}</h3>
                <p className="small">{t("strategy.observed_first")}: <b>{fmt.pct(s.observed.first_time_retention.rate)}</b> ({fmt.pct(s.observed.first_time_retention.ci_low, 0)}–{fmt.pct(s.observed.first_time_retention.ci_high, 0)}) · {t("strategy.observed_repeat")}: <b>{fmt.pct(s.observed.repeat_retention.rate)}</b> ({fmt.pct(s.observed.repeat_retention.ci_low, 0)}–{fmt.pct(s.observed.repeat_retention.ci_high, 0)}) · {t("strategy.observed_recurring")}: <b>{fmt.pct(s.observed.recurring_retention.rate)}</b></p>
                <h3 style={{ margin: "10px 0 4px" }}>{t("strategy.assumptions")}</h3>
                <ul className="small muted" style={{ paddingLeft: 18 }}>{s.assumptions.map((a) => <li key={a}>{a}</li>)}</ul>
              </Card>
            </>
          )}</Q>
        </div>
      </div>
    </>
  );
}
