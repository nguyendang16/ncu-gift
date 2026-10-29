import { useEffect, useState, type ReactNode } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { usePlan, useScenario } from "../api/hooks";
import type { Plan, PlanLever, Scenario } from "../api/types";
import { useAiDock } from "../components/ai/dockContext";
import { Chart } from "../components/Chart";
import { Icon, Notice, PageHeader, Q, useDebounced, type IconName } from "../components/ui";
import { useApp } from "../context/AppContext";
import { useI18n } from "../i18n";
import { fanOption } from "../lib/options";
import { addsOption, addsParts, rangeOption } from "../lib/planCharts";

type S = { r1: number; r2: number; mult: number; rec: number; gift: number };
const ZERO: S = { r1: 0, r2: 0, mult: 1, rec: 0, gift: 0 };
const GOALS = [500_000, 1_000_000, 2_000_000, 5_000_000];
const clamp = (v: number, lo: number, hi: number) => Math.min(Math.max(v, lo), hi);
const r1d = (v: number) => Math.round(v * 10) / 10;

/** How each way to get there maps onto the sliders. */
const WAYS: Record<string, { key: keyof S; icon: IconName; title: "gp.l_first" | "gp.l_repeat" | "gp.l_new" | "gp.l_rec"; max: number; set: (v: number) => Partial<S> }> = {
  first_time_retention_uplift_pts: { key: "r1", icon: "people", title: "gp.l_first", max: 20, set: (v) => ({ r1: r1d(clamp(v, 0, 20)) }) },
  repeat_retention_uplift_pts: { key: "r2", icon: "repeat", title: "gp.l_repeat", max: 10, set: (v) => ({ r2: r1d(clamp(v, 0, 10)) }) },
  new_donor_inflow_multiplier: { key: "mult", icon: "route", title: "gp.l_new", max: 50, set: (v) => ({ mult: Math.round(clamp(1 + v / 100, 0.5, 1.5) * 100) / 100 }) },
  recurring_conversion_pct: { key: "rec", icon: "calendar", title: "gp.l_rec", max: 30, set: (v) => ({ rec: r1d(clamp(v, 0, 30)) }) },
};

function Step({ n, title, sub, children }: { n: number; title: string; sub?: string; children: ReactNode }) {
  return (
    <section className="gp-step">
      <header><span className="n">{n}</span><div><h2>{title}</h2>{sub && <p>{sub}</p>}</div></header>
      {children}
    </section>
  );
}

function WayCard({ lever, plan, onTry }: { lever: PlanLever; plan: Plan; onTry: (patch: Partial<S>) => void }) {
  const { t, fmt } = useI18n();
  const w = WAYS[lever.lever];
  if (!w) return null;
  const ok = lever.reaches_target_alone;
  return (
    <article className={`gp-way ${ok ? "ok" : ""}`}>
      <header><span className="ico"><Icon name={w.icon} size={18} /></span><h3>{t(w.title)}</h3></header>
      {ok ? <p>{lever.what_it_takes}{lever.about_extra_donors ? <span className="muted"> · {t("gp.people", { n: fmt.int(lever.about_extra_donors) })}</span> : null}</p>
        : <p className="muted">{t("gp.notenough", { amount: lever.most_it_can_add?.text ?? "–" })}</p>}
      <footer>
        <span className={`pill ${ok ? "ok" : "neutral"}`}>{ok ? t("gp.enough") : t("gp.partial")}</span>
        <button className="btn" onClick={() => onTry({ ...ZERO, ...w.set(ok ? (lever.needed_setting ?? 0) : w.max) })}>{t("gp.try")}</button>
      </footer>
      <span className="sr-only">{plan.goal.extra_ordinary_giving.text}</span>
    </article>
  );
}

function Lever({ label, from, to, extra, value, min, max, step, onChange }: { label: string; from: string; to: string; extra?: string; value: number; min: number; max: number; step: number; onChange: (v: number) => void }) {
  const id = "gp-" + label.replace(/[^\w一-鿿]+/g, "-");
  return (
    <div className="gp-lever">
      <div className="row"><label htmlFor={id}>{label}</label><span className="val"><b>{from}</b> → <b className={to === from ? "" : "chg"}>{to}</b></span></div>
      <input id={id} type="range" min={min} max={max} step={step} value={value} onChange={(e) => onChange(Number(e.target.value))} />
      {extra && <div className="small muted">{extra}</div>}
    </div>
  );
}

export default function Strategy() {
  const { datasetId, settings } = useApp();
  const { t, fmt } = useI18n();
  const { ask } = useAiDock();
  // the AI analyst links here with its settings in the address, so the person keeps exploring from the same point
  const [qs] = useSearchParams();
  const num = (k: string, d: number) => { const v = Number(qs.get(k)); return qs.has(k) && Number.isFinite(v) ? v : d; };
  const [goal, setGoal] = useState(num("goal", qs.has("r1") || qs.has("mult") || qs.has("rec") ? 0 : 1_000_000));
  const [custom, setCustom] = useState("");
  const [s, setS] = useState<S>({ r1: num("r1", 0), r2: num("r2", 0), mult: num("mult", 1), rec: num("rec", 0), gift: num("gift", 0) });
  const [more, setMore] = useState(s.r2 > 0 || s.rec > 0 || s.gift > 0);
  const set = (p: Partial<S>) => setS((x) => ({ ...x, ...p }));

  const debGoal = useDebounced(goal, 450);
  const plan = usePlan(datasetId, debGoal > 0 ? debGoal : undefined, settings.exceptional);
  const body = useDebounced({ dataset_id: datasetId, exceptional_threshold: settings.exceptional, r1_uplift_pp: s.r1, r2_uplift_pp: s.r2, new_donor_multiplier: s.mult, recurring_conversion_pct: s.rec, major_gift_ntd: s.gift }, 250);
  const scen = useScenario(body);
  const base = useScenario({ dataset_id: datasetId, exceptional_threshold: settings.exceptional, r1_uplift_pp: 0, r2_uplift_pp: 0, new_donor_multiplier: 1, recurring_conversion_pct: 0, major_gift_ntd: 0 });
  useEffect(() => { if (custom && Number(custom) > 0) setGoal(Number(custom)); }, [custom]);

  const p = plan.data;
  const b = p?.balanced_effort;
  const mix = b && b.reaches_target !== false ? { r1: b.first_time_retention_uplift_points ?? 0, r2: b.repeat_retention_uplift_points ?? 0, mult: b.new_donor_inflow_multiplier ?? 1, rec: b.recurring_conversion_percent ?? 0, gift: 0 } : null;

  const result = (sc: Scenario) => {
    const delta = sc.scenario.delta_vs_baseline;
    const first = sc.observed.first_time_retention, rep = sc.observed.repeat_retention;
    const newBase = Math.round(sc.cohorts[2].donors / (s.mult || 1));
    return (
      <div className="gp-result">
        <div className="lbl">{t("gp.result_title", { year: sc.projection_year })}</div>
        <div className="big">{t("gp.about", { amount: fmt.compact(sc.scenario.expected) })}</div>
        <div className="small muted">{t("gp.range", { low: fmt.compact(sc.scenario.low), high: fmt.compact(sc.scenario.high) })}</div>
        <div className={`gp-delta ${delta > 0 ? "up" : delta < 0 ? "down" : ""}`}>
          {delta === 0 ? t("gp.same", { base: fmt.compact(sc.baseline.expected) }) : t("gp.vs", { delta: `${delta > 0 ? "+" : "−"}${fmt.compact(Math.abs(delta))}`, base: fmt.compact(sc.baseline.expected) })}
        </div>
        {goal > 0 && (
          <div className="gp-goal-bar">
            <div className="bar"><i className={delta >= goal ? "met" : ""} style={{ width: `${clamp((delta / goal) * 100, 0, 100)}%` }} /></div>
            <span className="small">{delta >= goal ? t("gp.goal_met", { goal: fmt.compact(goal) }) : t("gp.goal_pct", { pct: Math.max(0, Math.floor((delta / goal) * 100)), goal: fmt.compact(goal) })}</span>
          </div>
        )}
        <div className="gp-chart"><div className="cap">{t("gp.chart_range")}</div><Chart option={rangeOption(sc, fmt, t, goal)} height={170} label={t("strategy.range_aria")} /></div>
        {addsParts(sc).length > 0 && (
          <div className="gp-chart">
            <div className="cap">{t("gp.chart_adds")}</div>
            <Chart option={addsOption(addsParts(sc), fmt)} height={40 + 46 * addsParts(sc).length} label={t("gp.chart_adds")} />
          </div>
        )}
        <div className="gp-chart"><div className="cap">{t("gp.chart_history")}</div><Chart option={fanOption(sc, fmt, t, goal)} height={240} label={t("strategy.range_aria")} /></div>
        <p className="small muted gp-cap">{t("gp.caption")}</p>
        <div className="gp-btns">
          <button className="btn go" onClick={() => ask(goal > 0 ? t("gp.ask_goal", { goal: fmt.compact(goal) }) : t("gp.ask_plain"))}><Icon name="ai" size={15} />{t("gp.ask")}</button>
          <button className="btn" onClick={() => set(ZERO)}>{t("strategy.reset")}</button>
        </div>
        <details className="how gp-how">
          <summary>{t("gp.how")}</summary>
          <div className="body">
            <p>{t("gp.how_text")}</p>
            <div className="scroll"><table className="t">
              <thead><tr><th>{t("strategy.th_cohort")}</th><th className="r">{t("strategy.th_donors")}</th><th className="r">{t("strategy.th_chance")}</th><th className="r">{t("strategy.th_typical")}</th><th className="r">{t("strategy.th_expected")}</th></tr></thead>
              <tbody>{sc.cohorts.map((c) => (
                <tr key={c.cohort}><td>{c.cohort}</td><td className="r num">{fmt.int(c.donors)}</td>
                  <td className="r num">{c.retention_scenario == null ? "–" : fmt.pct(c.retention_scenario, 0)}</td>
                  <td className="r num">{fmt.ntd(c.avg_gift)}</td><td className="r num">{fmt.compact(c.expected_scenario)}</td></tr>
              ))}</tbody></table></div>
            <p className="small">{t("gp.example", { n: fmt.int(sc.cohorts[0].donors), rate: fmt.pct(sc.cohorts[0].retention_scenario ?? 0, 0), gift: fmt.ntd(sc.cohorts[0].avg_gift), amount: fmt.compact(sc.cohorts[0].expected_scenario) })}</p>
            <ul className="small muted" style={{ paddingLeft: 18 }}>{sc.assumptions.map((a) => <li key={a}>{a}</li>)}</ul>
          </div>
        </details>
        <span className="sr-only">{first.n}{rep.n}{newBase}</span>
      </div>
    );
  };

  return (
    <>
      <PageHeader title={t("strategy.title")} />
      <Notice tone="info">{t("gp.intro")}</Notice>
      <div className="gp">
        <div className="gp-main">
          <Step n={1} title={t("gp.s1")} sub={t("gp.s1_sub")}>
            <div className="gp-goals" role="group" aria-label={t("gp.s1")}>
              {GOALS.map((g) => <button key={g} className={`gp-chip ${goal === g && !custom ? "on" : ""}`} aria-pressed={goal === g && !custom} onClick={() => { setCustom(""); setGoal(g); }}>+{fmt.compact(g)}</button>)}
              <button className={`gp-chip ${goal === 0 ? "on" : ""}`} aria-pressed={goal === 0} onClick={() => { setCustom(""); setGoal(0); }}>{t("gp.chip_none")}</button>
              <label className="gp-other">{t("gp.custom")}<input type="number" min={0} step={100000} inputMode="numeric" value={custom} placeholder="1500000" onChange={(e) => setCustom(e.target.value)} /></label>
            </div>
            {base.data && <p className="gp-base">{t("gp.base_line", { amount: fmt.compact(base.data.baseline.expected), low: fmt.compact(base.data.baseline.low), high: fmt.compact(base.data.baseline.high) })}</p>}
          </Step>

          {goal > 0 && (
            <Step n={2} title={t("gp.s2")} sub={t("gp.s2_sub")}>
              <Q q={plan}>{(pl) => (
                <>
                  {mix && (
                    <article className="gp-way mix">
                      <header><span className="ico"><Icon name="ai" size={18} /></span><h3>{t("gp.mix_title")}</h3><span className="pill ok">{t("gp.recommended")}</span></header>
                      <p>{t("gp.mix_sub")}</p>
                      <ul className="gp-mixlist">
                        <li>{t("gp.mix_first", { x: mix.r1 })}</li><li>{t("gp.mix_repeat", { x: mix.r2 })}</li>
                        <li>{t("gp.mix_new", { x: r1d((mix.mult - 1) * 100) })}</li><li>{t("gp.mix_rec", { x: mix.rec })}</li>
                      </ul>
                      <footer><span className="muted small">{b?.adds_about ? t("gp.mix_adds", { amount: b.adds_about.text }) : ""}</span><button className="btn go" onClick={() => setS(mix)}>{t("gp.use_mix")}</button></footer>
                    </article>
                  )}
                  {b?.reaches_target === false && <Notice tone="warn">{t("gp.mix_cannot", { amount: b.most_all_levers_can_add?.text ?? "–" })}</Notice>}
                  <div className="gp-ways">
                    {pl.levers_each_on_its_own.map((l) => <WayCard key={l.lever} lever={l} plan={pl} onTry={(patch) => setS({ ...ZERO, ...patch })} />)}
                    {pl.money_at_risk && (
                      <article className="gp-way">
                        <header><span className="ico"><Icon name="phone" size={18} /></span><h3>{t("gp.risk_title")}</h3></header>
                        <p>{typeof pl.money_at_risk.share_of_top_20_to_keep_to_reach_goal === "string"
                          ? t("gp.risk_cannot", { amount: pl.money_at_risk.top_20_value_at_risk.text })
                          : t("gp.risk_text", { pct: pl.money_at_risk.share_of_top_20_to_keep_to_reach_goal.text, amount: pl.money_at_risk.top_20_value_at_risk.text })}</p>
                        <footer><span /><Link className="btn" to="/risk">{t("gp.risk_open")} →</Link></footer>
                      </article>
                    )}
                  </div>
                  {pl.typical_gifts.extra_gifts_needed_at_median ? <p className="small muted">{t("gp.gifts_text", { n: fmt.int(pl.typical_gifts.extra_gifts_needed_at_median), gift: pl.typical_gifts.median_gift?.text ?? "" })}</p> : null}
                </>
              )}</Q>
            </Step>
          )}

          <Step n={goal > 0 ? 3 : 2} title={t("gp.s3")} sub={t("gp.s3_sub")}>
            {scen.data ? (() => {
              const sc = scen.data, first = sc.observed.first_time_retention, rep = sc.observed.repeat_retention;
              const newBase = Math.round(sc.cohorts[2].donors / (s.mult || 1));
              return (
                <>
                  <Lever label={t("gp.sl_first")} from={fmt.pct(first.rate, 0)} to={fmt.pct(clamp(first.rate + s.r1 / 100, 0, 1), 0)} value={s.r1} min={0} max={20} step={0.1} onChange={(r1) => set({ r1 })}
                    extra={s.r1 > 0 ? t("gp.people", { n: fmt.int(Math.round(first.n * s.r1 / 100)) }) : t("gp.of_n", { n: fmt.int(first.n) })} />
                  <Lever label={t("gp.sl_new")} from={fmt.int(newBase)} to={fmt.int(Math.round(newBase * s.mult))} value={s.mult} min={0.5} max={1.5} step={0.01} onChange={(mult) => set({ mult })}
                    extra={s.mult !== 1 ? t("gp.people_pct", { n: fmt.int(Math.round(newBase * (s.mult - 1))), pct: Math.round((s.mult - 1) * 100) }) : t("gp.new_hint")} />
                  <button className="gp-more" aria-expanded={more} onClick={() => setMore(!more)}>{more ? t("gp.fewer") : t("gp.more")}</button>
                  {more && (
                    <>
                      <Lever label={t("gp.sl_repeat")} from={fmt.pct(rep.rate, 0)} to={fmt.pct(clamp(rep.rate + s.r2 / 100, 0, 1), 0)} value={s.r2} min={0} max={10} step={0.1} onChange={(r2) => set({ r2 })}
                        extra={s.r2 > 0 ? t("gp.people", { n: fmt.int(Math.round(rep.n * s.r2 / 100)) }) : t("gp.of_n", { n: fmt.int(rep.n) })} />
                      <Lever label={t("gp.sl_rec")} from="0%" to={`${s.rec}%`} value={s.rec} min={0} max={30} step={0.5} onChange={(rec) => set({ rec })} />
                      <label className="gp-gift">{t("gp.sl_gift")}
                        <select value={s.gift} onChange={(e) => set({ gift: Number(e.target.value) })}>
                          {[0, 5e6, 2e7, 5e7].map((v) => <option key={v} value={v}>{v ? fmt.ntd(v) : t("strategy.none")}</option>)}
                        </select>
                      </label>
                    </>
                  )}
                </>
              );
            })() : <p className="muted">{t("ui.loading")}</p>}
          </Step>
        </div>
        <aside className="gp-side"><Q q={scen}>{(sc) => result(sc)}</Q></aside>
      </div>
    </>
  );
}
