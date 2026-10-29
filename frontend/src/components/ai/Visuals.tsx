import { useState } from "react";
import { Link } from "react-router-dom";
import { useScenario } from "../../api/hooks";
import type { AgentStep, Scenario, TrendRow } from "../../api/types";
import { useApp } from "../../context/AppContext";
import { useI18n, type Fmt } from "../../i18n";
import { C, axisText, baseOption, yMoney } from "../../lib/chart";
import { bubbleOption, concentrationOption, donutOption, fanOption, heatmapOption, sankeyOption, waterfallOption, type T } from "../../lib/options";
import { Chart } from "../Chart";
import { useDebounced } from "../ui";

type V = { type: string; [k: string]: unknown };

/** Ordinary and exceptional giving by year, with donors as a line: the compact version of the Overview chart. */
function trendOption(rows: TrendRow[], fmt: Fmt, t: T) {
  const b = baseOption();
  return {
    ...b, tooltip: { ...b.tooltip, valueFormatter: (v: number) => fmt.ntd(v) },
    legend: { bottom: 0, left: "center", icon: "roundRect" as const, itemWidth: 10, itemHeight: 10, textStyle: { color: C.muted, fontSize: 12 } },
    grid: { left: 6, right: 40, top: 22, bottom: 36, containLabel: true },
    xAxis: { type: "category" as const, data: rows.map((r) => String(r.year)), axisLabel: axisText },
    yAxis: [yMoney(fmt.axisMoney), { type: "value" as const, axisLabel: axisText, splitLine: { show: false }, min: 0 }],
    series: [
      { name: t("series.ordinary"), type: "bar" as const, stack: "t", barMaxWidth: 56, data: rows.map((r) => r.regular), itemStyle: { color: C.regular } },
      { name: t("series.exceptional"), type: "bar" as const, stack: "t", barMaxWidth: 56, data: rows.map((r) => r.exceptional), itemStyle: { color: C.exceptional, borderRadius: [6, 6, 0, 0] } },
      { name: t("series.donors"), type: "line" as const, yAxisIndex: 1, data: rows.map((r) => r.donors), symbol: "circle", symbolSize: 8, lineStyle: { width: 3, color: C.indigo }, itemStyle: { color: C.indigo }, tooltip: { valueFormatter: (v: number) => fmt.int(v) } },
    ],
  };
}

function Slider({ label, value, min, max, step, onChange, text }: { label: string; value: number; min: number; max: number; step: number; onChange: (v: number) => void; text: string }) {
  return (
    <label className="wi-slider">
      <span className="row"><span>{label}</span><b className="num">{text}</b></span>
      <input type="range" min={min} max={max} step={step} value={value} onChange={(e) => onChange(Number(e.target.value))} />
    </label>
  );
}

/** A what-if you can move: the same calculation as the Strategy explorer, right inside the answer. No AI is involved when you drag. */
function WhatIf({ v }: { v: { settings: { r1: number; r2: number; mult: number; rec: number; gift: number }; scenario: Scenario; goal?: number } }) {
  const { t, fmt } = useI18n();
  const { datasetId, settings: app } = useApp();
  const [s, setS] = useState(v.settings);
  const body = useDebounced({ dataset_id: datasetId, exceptional_threshold: app.exceptional, r1_uplift_pp: s.r1, r2_uplift_pp: s.r2, new_donor_multiplier: s.mult, recurring_conversion_pct: s.rec, major_gift_ntd: s.gift }, 250);
  const q = useScenario(body);
  const sc = q.data ?? v.scenario;
  const delta = sc.scenario.delta_vs_baseline;
  const link = `/strategy?r1=${s.r1}&r2=${s.r2}&mult=${s.mult}&rec=${s.rec}&gift=${s.gift}`;
  const moved = s.r1 !== v.settings.r1 || s.r2 !== v.settings.r2 || s.mult !== v.settings.mult || s.rec !== v.settings.rec;
  return (
    <div className="wi">
      <div className="wi-kpis">
        <div><span className="l">{t("strategy.baseline")}</span><b>{fmt.compact(sc.baseline.expected)}</b></div>
        <div className="arrow">→</div>
        <div className="hi"><span className="l">{t("strategy.scenario")}</span><b>{fmt.compact(sc.scenario.expected)}</b><span className={`d ${delta >= 0 ? "up" : "down"}`}>{delta >= 0 ? "+" : "−"}{fmt.compact(Math.abs(delta))}</span></div>
      </div>
      {v.goal ? (
        <div className="wi-goal" title={t("ai.wi_goal", { goal: fmt.compact(v.goal) })}>
          <div className="bar"><i style={{ width: `${Math.max(0, Math.min(100, (delta / v.goal) * 100))}%` }} /></div>
          <span className="small">{t("ai.wi_goal_pct", { goal: fmt.compact(v.goal), pct: Math.max(0, Math.round((delta / v.goal) * 100)) })}</span>
        </div>
      ) : null}
      <Chart option={fanOption(sc, fmt, t)} height={190} label={t("strategy.range_aria")} />
      <div className="wi-sliders">
        <Slider label={t("strategy.l_first")} value={s.r1} min={0} max={20} step={0.5} onChange={(r1) => setS({ ...s, r1 })} text={t("strategy.pp", { n: `+${s.r1}` })} />
        <Slider label={t("strategy.l_repeat")} value={s.r2} min={0} max={10} step={0.5} onChange={(r2) => setS({ ...s, r2 })} text={t("strategy.pp", { n: `+${s.r2}` })} />
        <Slider label={t("strategy.l_inflow")} value={s.mult} min={0.5} max={1.5} step={0.05} onChange={(mult) => setS({ ...s, mult })} text={`× ${s.mult.toFixed(2)}`} />
        <Slider label={t("strategy.l_recurring")} value={s.rec} min={0} max={30} step={0.5} onChange={(rec) => setS({ ...s, rec })} text={`${s.rec}%`} />
      </div>
      <div className="wi-foot">
        {moved && <button className="btn" onClick={() => setS(v.settings)}>{t("strategy.reset")}</button>}
        <Link className="btn go" to={link}>{t("ai.wi_open")} →</Link>
      </div>
    </div>
  );
}

/** The chart or card an analysis drew for itself, shown inside the answer so the evidence can be seen, not just read. */
export function Visual({ step }: { step: AgentStep }) {
  const { t, fmt } = useI18n();
  const v = step.visual as V | null | undefined;
  if (!v) return null;
  const d = v.data as never, label = step.title;
  let body = null;
  switch (v.type) {
    case "trend": body = <Chart option={trendOption(v.rows as TrendRow[], fmt, t)} height={230} label={label} />; break;
    case "bridge": body = <Chart option={waterfallOption(d, "ordinary", fmt, t)} height={240} label={label} />; break;
    case "concentration": body = <Chart option={concentrationOption(d, t)} height={230} label={label} />; break;
    case "season": body = <Chart option={heatmapOption(d, fmt)} height={120 + 40 * ((d as { years: number[] }).years?.length ?? 3)} label={label} />; break;
    case "donut": body = <Chart option={donutOption(v.rows as never, fmt)} height={230} label={label} />; break;
    case "sankey": body = <Chart option={sankeyOption(d, t)} height={250} label={label} />; break;
    case "bubble": body = (v.points as unknown[]).length ? <Chart option={bubbleOption(v.points as never, fmt, t)} height={250} label={label} /> : null; break;
    case "whatif": body = <WhatIf v={v as never} />; break;
  }
  if (!body) return null;
  return <figure className="vis"><figcaption>{step.title}</figcaption>{body}</figure>;
}
