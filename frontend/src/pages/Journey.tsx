import { useJourney } from "../api/hooks";
import type { Journey } from "../api/types";
import { Chart } from "../components/Chart";
import { Card, Notice, PageHeader, Q } from "../components/ui";
import { useApp } from "../context/AppContext";
import { useI18n, type Fmt } from "../i18n";
import type { Key } from "../i18n/en";
import { C, axisText, baseOption } from "../lib/chart";
import { sankeyOption } from "../lib/options";

type T = (key: Key, params?: Record<string, string | number>) => string;

function flowOption(j: Journey, t: T) {
  const ys = j.years.filter((y) => y.history_available);
  const b = baseOption();
  const s = (name: string, key: "new" | "retained" | "reactivated", color: string) => ({ name, type: "bar" as const, stack: "pos", data: ys.map((y) => y[key] ?? 0), itemStyle: { color }, barMaxWidth: 64 });
  return {
    ...b,
    xAxis: { type: "category" as const, data: ys.map((y) => String(y.year)), axisLabel: axisText },
    yAxis: { type: "value" as const, axisLabel: axisText, splitLine: { lineStyle: { color: C.line } } },
    series: [
      s(t("state.new"), "new", C.regular), s(t("state.retained"), "retained", C.indigo), s(t("state.reactivated"), "reactivated", C.sky),
      { name: t("state.lapsed"), type: "bar" as const, stack: "neg", data: ys.map((y) => -(y.lapsed ?? 0)), itemStyle: { color: C.grey }, barMaxWidth: 64 },
    ],
  };
}

function Rate({ label, n, returned, rate, lo, hi }: { label: string; n: number; returned: number; rate: number; lo: number; hi: number }) {
  const { t, fmt } = useI18n();
  return (
    <div style={{ marginBottom: 14 }}>
      <div className="small" style={{ display: "flex", justifyContent: "space-between", gap: 8 }}>
        <span>{label}</span><span className="muted num">{t("journey.of", { k: returned, n })}</span>
      </div>
      <div className="rate" role="img" aria-label={t("journey.rate_aria", { label, rate: fmt.pct(rate), lo: fmt.pct(lo), hi: fmt.pct(hi) })}>
        <div className="fill" style={{ width: `${rate * 100}%` }} />
        <div className="ci" style={{ left: `${lo * 100}%`, width: `${Math.max((hi - lo) * 100, 0.6)}%` }} />
        <span className="lbl">{fmt.pct(rate, 0)}</span>
      </div>
      <div className="legend-note">{t("journey.interval", { lo: fmt.pct(lo, 0), hi: fmt.pct(hi, 0) })}</div>
    </div>
  );
}

export default function JourneyPage() {
  const { datasetId } = useApp();
  const { t, fmt } = useI18n();
  const q = useJourney(datasetId);
  const f: Fmt = fmt;
  return (
    <>
      <PageHeader title={t("journey.title")} question={t("q.journey")} desc={t("journey.desc")} />
      <Q q={q}>{(j) => (
        <>
          <Card icon="route" title={t("sankey.title")} sub={t("sankey.sub")} help="tip.sankey">
            <Chart option={sankeyOption(j, t)} label={t("sankey.aria")} height={340} />
            <div className="how">{t("how.sankey")}</div>
          </Card>
          <div className="grid g-main">
            <Card icon="trend" title={t("journey.flow_title")} sub={t("journey.flow_sub")}>
              <Chart option={flowOption(j, t)} label={t("journey.flow_aria")} height={310} />
            </Card>
            <Card icon="repeat" title={t("journey.funnel_title")} sub={t("journey.funnel_sub")}>
              {j.funnel.length === 0 && <p className="muted">{t("journey.needs_three")}</p>}
              {j.funnel.map((r) => (
                <div key={r.cohort_year}>
                  <h3 style={{ marginBottom: 8 }}>{r.cohort_year} → {r.next_year}</h3>
                  <Rate label={t("journey.cohort_first", { year: r.cohort_year })} n={r.first_time.n} returned={r.first_time.returned} rate={r.first_time.rate} lo={r.first_time.ci_low} hi={r.first_time.ci_high} />
                  <Rate label={t("journey.cohort_repeat", { prev: r.cohort_year - 1, year: r.cohort_year })} n={r.repeat.n} returned={r.repeat.returned} rate={r.repeat.rate} lo={r.repeat.ci_low} hi={r.repeat.ci_high} />
                </div>
              ))}
            </Card>
          </div>
          <Card icon="data" title={t("journey.states_title")} sub={t("journey.states_sub")}>
            <div className="scroll">
              <table className="t">
                <thead><tr><th>{t("col.year")}</th><th className="r">{t("state.active")}</th><th className="r">{t("state.new")}</th><th className="r">{t("state.retained")}</th><th className="r">{t("state.reactivated")}</th><th className="r">{t("state.lapsed")}</th></tr></thead>
                <tbody>
                  {j.years.map((y) => (
                    <tr key={y.year}>
                      <td>{y.year}</td><td className="r num">{f.int(y.active)}</td>
                      {y.history_available ? <><td className="r num">{f.int(y.new)}</td><td className="r num">{f.int(y.retained)}</td><td className="r num">{f.int(y.reactivated)}</td><td className="r num">{f.int(y.lapsed)}</td></>
                        : <td colSpan={4} className="muted small">{t("journey.first_year_note")}</td>}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>
          <div style={{ height: 16 }} />
          <Notice tone="info">{j.notes.join(" ")}</Notice>
        </>
      )}</Q>
    </>
  );
}
