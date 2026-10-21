import type { ReactNode } from "react";
import { useEffect, useRef, useState } from "react";
import { flushSync } from "react-dom";
import { Link, useLocation } from "react-router-dom";
import { useBridge, useClassCompare, useConcentration, useHighlights, useOverview, usePurposeTree, useSeasonality, useTrend } from "../api/hooks";
import type { Breakdown } from "../api/types";
import { AiSummary } from "../components/AiParts";
import { Chart } from "../components/Chart";
import { PurposeBoard } from "../components/PurposeBoard";
import { Accordion, Bar, Card, Icon, Notice, PageHeader, Q, Section, Seg, type IconName } from "../components/ui";
import { useApp } from "../context/AppContext";
import { useI18n } from "../i18n";
import type { Key } from "../i18n/en";
import { captureChartPngs, chartCount, downloadBytes, textBytes, toCsv, zipStore } from "../lib/download";
import { buildOverviewExport } from "../lib/overviewExport";
import { bubbleOption as _unused, classCompareOption, comboOption, concentrationOption, donutOption, hbar, heatmapOption, kpiCompareOption, monthlyOption, waterfallOption } from "../lib/options";

void _unused;

function BreakdownTable({ rows, first }: { rows: Breakdown[]; first: string }) {
  const { t, fmt } = useI18n();
  const max = Math.max(...rows.map((r) => r.share_amount ?? 0), 0.0001);
  return (
    <div className="scroll">
      <table className="t">
        <thead><tr><th>{first}</th><th className="r">{t("col.amount")}</th><th className="r">{t("col.gifts")}</th><th style={{ width: 130 }}>{t("col.share")}</th></tr></thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.label}>
              <td>{r.label}</td>
              <td className="r num">{r.amount == null ? t("ui.na") : fmt.ntd(r.amount)}</td>
              <td className="r num">{fmt.int(r.count)}</td>
              <td>{r.share_amount == null ? <span className="muted small">{t("ui.na")}</span> : <div style={{ display: "flex", gap: 8, alignItems: "center" }}><Bar value={r.share_amount} max={max} /><span className="small num muted">{fmt.pct(r.share_amount, 0)}</span></div>}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// "+NT$12M" / "−NT$205M": the sign goes outside the currency, as people write it
const signedWith = (f: (x: number) => string) => (v: number) => `${v < 0 ? "−" : "+"}${f(Math.abs(v))}`;

function toneOf(delta: number | null | undefined): "" | "up" | "down" {
  if (delta == null || delta === 0) return "";
  return delta > 0 ? "up" : "down";
}

function HeroStat({ label, value, detail, tone }: { label: string; value: ReactNode; detail?: ReactNode; tone?: "" | "up" | "down" | "na" }) {
  return (
    <div className={`hero-stat ${tone ?? ""}`}>
      <div className="l">{label}</div>
      <div className="v">{value}</div>
      <div className="d">{detail || " "}</div>
    </div>
  );
}

export default function Overview() {
  const { datasetId, settings } = useApp();
  const { t, tx, fmt } = useI18n();
  const loc = useLocation();
  const signed = signedWith(fmt.compact);
  const [year, setYear] = useState<number | undefined>();
  const [compareYear, setCompareYear] = useState<number | undefined>();
  const [scope, setScope] = useState<"all" | "regular">("all");
  const [log, setLog] = useState(false);
  const [mode, setMode] = useState<"ordinary" | "all">("ordinary");
  const [tablesOpen, setTablesOpen] = useState(false);
  const [exporting, setExporting] = useState(false);
  const holdToggle = useRef(false);
  const [bandLow, setBandLow] = useState("500000");
  const [bandHigh, setBandHigh] = useState("1000000");
  const lowCut = Number(bandLow);
  const highCut = Number(bandHigh);
  const cutsOk = lowCut > 0 && highCut > lowCut;
  const bandCuts = useRef({ low: 500_000, high: 1_000_000 });
  if (cutsOk) bandCuts.current = { low: lowCut, high: highCut };
  const [classMin, setClassMin] = useState("");
  const [classMax, setClassMax] = useState("");
  const minCut = classMin.trim() === "" ? undefined : Number(classMin);
  const maxCut = classMax.trim() === "" ? undefined : Number(classMax);
  const rangeOk = (minCut === undefined || (Number.isFinite(minCut) && minCut >= 0))
    && (maxCut === undefined || (Number.isFinite(maxCut) && maxCut >= 0))
    && (minCut === undefined || maxCut === undefined || minCut <= maxCut);
  const classWindow = useRef<{ min?: number; max?: number }>({});
  if (rangeOk) classWindow.current = { min: minCut, max: maxCut };
  const trend = useTrend(datasetId, settings.exceptional, bandCuts.current);
  const classes = useClassCompare(datasetId, { scope, exceptional: settings.exceptional, min: classWindow.current.min, max: classWindow.current.max });
  const ov = useOverview(datasetId, { year, compareYear, scope, exceptional: settings.exceptional, large: settings.large, returnDef: settings.returnDef });
  const y = ov.data?.year;
  const hl = useHighlights(datasetId, y, settings.exceptional, compareYear);
  const bridge = useBridge(datasetId, y, settings.exceptional, compareYear);
  const conc = useConcentration(datasetId, y, settings.exceptional);
  const season = useSeasonality(datasetId, settings.exceptional);
  const tree = usePurposeTree(datasetId, y, settings.exceptional);

  // links such as "/#concentration" scroll to their section once the page has drawn
  useEffect(() => {
    if (loc.hash && ov.data) setTimeout(() => document.querySelector(loc.hash)?.scrollIntoView({ behavior: "smooth", block: "start" }), 250);
  }, [loc.hash, ov.data]);

  const chartsReady = [trend, bridge, tree, season, conc, hl].every((q) => q.isFetched);

  async function downloadView() {
    const overview = ov.data;
    if (!overview || exporting || !chartsReady) return;
    const wasOpen = tablesOpen;
    holdToggle.current = true;
    setExporting(true);
    flushSync(() => setTablesOpen(true));
    let lastCount = -1;
    let steady = 0;
    for (let i = 0; i < 25 && steady < 2; i++) {
      await new Promise((resolve) => setTimeout(resolve, 80));
      const count = chartCount();
      steady = count > 0 && count === lastCount ? steady + 1 : 0;
      lastCount = count;
    }
    try {
      const built = buildOverviewExport({
        t, fmt, overview, trend: trend.data ?? [], highlights: hl.data ?? [],
        bridge: bridge.data, concentration: conc.data, tree: tree.data,
        returnLabel: t(`return.${settings.returnDef}` as Key),
        bands: bandCuts.current,
        classCompare: classes.data,
        exceptional: settings.exceptional, large: settings.large,
      });
      const folder = `ncu-gift-${overview.year}`;
      const zip = zipStore([
        { path: `${folder}/summary.txt`, bytes: textBytes(built.summary) },
        { path: `${folder}/tables.csv`, bytes: textBytes(toCsv(built.tables)) },
        ...captureChartPngs().map((chart) => ({ path: `${folder}/charts/${chart.name}`, bytes: chart.bytes })),
      ]);
      downloadBytes(`${folder}.zip`, zip, "application/zip");
    } finally {
      setExporting(false);
      if (!wasOpen) setTablesOpen(false);
      setTimeout(() => { holdToggle.current = false; }, 300);
    }
  }

  return (
    <>
      <PageHeader title={t("overview.title")} question={t("q.overview")} desc={t("overview.desc")}>
        <label className="field">{t("overview.year")}
          <select value={y ?? ""} onChange={(e) => {
            const next = Number(e.target.value);
            setYear(next);
            setCompareYear((current) => (current === next ? undefined : current));
          }}>
            {(ov.data?.years ?? []).map((v) => <option key={v}>{v}</option>)}
          </select>
        </label>
        <label className="field">{t("overview.compare")}
          <select value={compareYear && compareYear !== y ? compareYear : (ov.data?.prev_year ?? "")} onChange={(e) => setCompareYear(Number(e.target.value))}>
            {(ov.data?.years ?? []).filter((v) => v !== y).map((v) => <option key={v} value={v}>{v}</option>)}
          </select>
        </label>
        <div className="field">{t("overview.scope")}
          <Seg label={t("overview.scope")} value={scope} onChange={setScope} options={[{ v: "all", l: t("scope.all") }, { v: "regular", l: t("scope.regular") }]} />
        </div>
        <div className="field">{t("export.pack_hint")}
          <button type="button" className="btn primary" title={t("export.pack_hint")} disabled={!ov.data || !chartsReady || exporting} onClick={() => { void downloadView(); }}>{exporting ? t("export.working") : t("export.pack")}</button>
        </div>
      </PageHeader>
      <Q q={ov}>{(o) => {
        const k = o.kpis;
        const signedCount = (n: number) => `${n > 0 ? "+" : n < 0 ? "−" : ""}${fmt.int(Math.abs(n))}`;
        const ratioText = (n: number | null) => (n == null ? "" : String(Math.round(n * 10) / 10));
        const avgText = (n: number | null) => (n == null ? "" : String(Math.round(n * 10) / 10));
        return (
          <>
            <div className="hero rise">
              <div className="eyebrow">{t("hero.eyebrow", { year: o.year })}</div>
              <p className="headline">{o.prev_year != null && k.regular_yoy_pct != null
                ? tx("hero.sentence", { year: o.year, compare: o.prev_year, total: fmt.compact(k.total), ordinary: fmt.compact(k.regular_total), change: fmt.signedPct(k.regular_yoy_pct) })
                : tx("hero.sentence_first", { year: o.year, total: fmt.compact(k.total), ordinary: fmt.compact(k.regular_total) })}</p>
              <div className="hero-stats">
                <HeroStat tone={toneOf(k.total_yoy_pct)} label={t("kpi.total", { year: o.year })} value={fmt.compact(k.total)}
                  detail={k.prev_total != null && k.total_yoy_pct != null && o.prev_year != null ? t("kpi.total_prev", { year: o.prev_year, amount: fmt.compact(k.prev_total), change: fmt.signedPct(k.total_yoy_pct) }) : undefined} />
                <HeroStat tone={toneOf(k.regular_yoy_pct)} label={t("kpi.ordinary_hero")}
                  value={k.regular_yoy_pct != null ? fmt.signedPct(k.regular_yoy_pct) : fmt.compact(k.regular_total)}
                  detail={k.prev_regular_total != null ? `${fmt.compact(k.prev_regular_total)} → ${fmt.compact(k.regular_total)}` : fmt.compact(k.regular_total)} />
                <HeroStat tone={toneOf(k.repeat_delta)} label={t("kpi.repeat_hero")} value={k.repeat_selected == null ? t("ui.na") : fmt.int(k.repeat_selected)}
                  detail={o.prev_year == null ? t(`return.${settings.returnDef}` as Key)
                    : k.repeat_delta == null ? t(`return.${settings.returnDef}_vs` as Key, { year: o.prev_year })
                    : k.repeat_ratio == null ? t("kpi.vs_people_noratio", { year: o.prev_year, delta: signedCount(k.repeat_delta) })
                    : t("kpi.vs_people", { year: o.prev_year, delta: signedCount(k.repeat_delta), ratio: ratioText(k.repeat_ratio) })} />
                <HeroStat tone={k.card_gifts == null ? "na" : toneOf(k.card_delta)} label={t("kpi.card")} value={k.card_gifts == null ? t("ui.na") : fmt.int(k.card_gifts)}
                  detail={k.card_gifts == null ? t("kpi.card_missing")
                    : k.card_delta == null || o.prev_year == null ? undefined
                    : k.card_yoy_pct == null ? t("kpi.vs_gifts_nopct", { year: o.prev_year, delta: signedCount(k.card_delta) })
                    : t("kpi.vs_gifts", { year: o.prev_year, delta: signedCount(k.card_delta), pct: fmt.signedPct(k.card_yoy_pct) })} />
                <HeroStat tone={toneOf(k.large_delta)} label={t("kpi.large", { threshold: fmt.compact(settings.large) })} value={fmt.int(k.large_gifts)}
                  detail={<>
                    {k.large_delta != null && o.prev_year != null && <div>{t("kpi.vs_gifts_nopct", { year: o.prev_year, delta: signedCount(k.large_delta) })}</div>}
                    {k.large_prior_avg != null && <div>{t("kpi.large_avg", { avg: avgText(k.large_prior_avg) })}</div>}
                  </>} />
                <HeroStat label={t("kpi.million")} value={fmt.pct(k.million_share, 0)}
                  detail={<>
                    <div>{t("kpi.million_sub", { count: k.million_projects, amount: fmt.compact(k.million_amount) })}</div>
                    {k.top_project_share != null && <div>{t("kpi.million_top", { pct: fmt.pct(k.top_project_share, 0) })}</div>}
                  </>} />
                <HeroStat tone="na" label={t("kpi.acct_income")} value={t("ui.na")} detail={t("kpi.acct_missing")} />
                <HeroStat tone="na" label={t("kpi.acct_balance")} value={t("ui.na")} detail={t("kpi.acct_missing")} />
                <HeroStat label={t("kpi.donors")} value={fmt.int(k.donors)} detail={t("kpi.donors_sub", { records: fmt.int(k.records), inkind: k.in_kind_records })} />
              </div>
            </div>

            <div style={{ marginBottom: 18 }}><AiSummary year={o.year} /></div>

            <Q q={hl}>{(cards) => cards.length > 0 && (
              <Section title={t("sec.next")} desc={t("sec.next_desc")}>
                <div className="hl-grid">
                  {cards.map((c) => (
                    <Link key={c.id} to={c.link} className={`hl ${c.tone}`}>
                      <span className="ico"><Icon name={c.icon as IconName} size={22} /></span>
                      <h3>{c.title}</h3><p>{c.text}</p><span className="go">{t("hl.open")} →</span>
                    </Link>
                  ))}
                </div>
              </Section>
            )}</Q>

            <Section title={t("sec.numbers")} desc={t("sec.numbers_desc")}>
              {(() => {
                const moneyLabels = [t("kpi.total_axis"), t("kpi.ordinary"), t("kpi.exceptional"), t("kpi.large_amount"), t("kpi.card_amount")];
                const countLabels = [t("kpi.donors"), t("kpi.repeat"), t("kpi.large_count"), t("kpi.exceptional_n"), t("kpi.card")];
                const moneySeries = o.kpi_compare.map((row) => ({ year: row.year, values: [row.total, row.regular_total, row.exceptional_total, row.large_gifts_amount, row.card_amount] }));
                const countSeries = o.kpi_compare.map((row) => ({ year: row.year, values: [row.donors, row.repeat, row.large_gifts, row.n_exceptional, row.card_gifts] }));
                return (
                  <Card icon="trend" title={t("chart.kpi_title")} sub={o.kpi_compare.map((row) => row.year).join(" · ")}>
                    <div className="grid g2">
                      <div>
                        <h3 className="small" style={{ marginBottom: 6 }}>{t("chart.kpi_money")}</h3>
                        <Chart option={kpiCompareOption(moneyLabels, moneySeries, fmt, true)} label={t("chart.kpi_money")} exportName={t("chart.kpi_money")} height={320} />
                      </div>
                      <div>
                        <h3 className="small" style={{ marginBottom: 6 }}>{t("chart.kpi_counts")}</h3>
                        <Chart option={kpiCompareOption(countLabels, countSeries, fmt, false)} label={t("chart.kpi_counts")} exportName={t("chart.kpi_counts")} height={320} />
                      </div>
                    </div>
                    <p className="muted small">{t("chart.kpi_repeat_note")}</p>
                    <div className="scroll">
                      <table className="t">
                        <thead>
                          <tr>
                            <th>{t("col.year")}</th>
                            <th className="r">{t("kpi.total_axis")}</th>
                            <th className="r">{t("kpi.ordinary")}</th>
                            <th className="r">{t("kpi.exceptional")}</th>
                            <th className="r">{t("kpi.donors")}</th>
                            <th className="r">{t("kpi.repeat")}</th>
                            <th className="r">{t("kpi.large_count")}</th>
                            <th className="r">{t("kpi.large_amount")}</th>
                            <th className="r">{t("kpi.card_amount")}</th>
                            <th className="r">{t("kpi.card")}</th>
                          </tr>
                        </thead>
                        <tbody>
                          {o.kpi_compare.map((row) => (
                            <tr key={row.year}>
                              <td>{row.year}</td>
                              <td className="r num">{fmt.axisMoney(row.total)}</td>
                              <td className="r num">{fmt.axisMoney(row.regular_total)}</td>
                              <td className="r num">{fmt.axisMoney(row.exceptional_total)}</td>
                              <td className="r num">{fmt.int(row.donors)}</td>
                              <td className="r num">{fmt.int(row.repeat)}</td>
                              <td className="r num">{fmt.int(row.large_gifts)}</td>
                              <td className="r num">{fmt.axisMoney(row.large_gifts_amount)}</td>
                              <td className="r num">{row.card_amount == null ? t("ui.na") : fmt.axisMoney(row.card_amount)}</td>
                              <td className="r num">{fmt.int(row.card_gifts)}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </Card>
                );
              })()}
            </Section>

            <Section title={t("sec.change")} desc={t("sec.change_desc")}>
              <div className="grid" style={{ gridTemplateColumns: "repeat(auto-fit, minmax(min(100%, 380px), 1fr))" }}>
                <Card icon="trend" title={t("chart.total_title")} sub={t("chart.total_sub")}>
                  <div className="band-cuts">
                    <label className="field">{t("chart.band_low")}
                      <input type="number" min={1} step={10000} value={bandLow} onChange={(e) => setBandLow(e.target.value)} />
                    </label>
                    <label className="field">{t("chart.band_high")}
                      <input type="number" min={1} step={10000} value={bandHigh} onChange={(e) => setBandHigh(e.target.value)} />
                    </label>
                  </div>
                  {!cutsOk && <p className="muted small">{t("chart.band_order")}</p>}
                  <Q q={trend}>{(r) => <Chart option={comboOption(r, bandCuts.current, fmt, t)} label={t("chart.total_aria")} exportName={t("chart.total_title")} height={360} />}</Q>
                  <div className="how">{t("how.combo")}</div>
                </Card>
                <Card icon="chart" title={t("chart.bridge_title")} sub={t("chart.bridge_sub", { year: o.year, compare: o.prev_year ?? "–" })} help="tip.bridge"
                  right={<Seg label={t("chart.bridge_mode")} value={mode} onChange={setMode} options={[{ v: "ordinary", l: t("scope.ordinary") }, { v: "all", l: t("scope.all") }]} />}>
                  <Q q={bridge}>{(b) => (
                    <>
                      <Chart option={waterfallOption(b, mode, fmt, t)} label={t("chart.bridge_aria")} exportName={t("chart.bridge_title")} height={310} />
                      {mode === "ordinary" && <div className="how">{t("how.bridge_exc", { change: signed(b.exceptional_end - b.exceptional_start) })}</div>}
                    </>
                  )}</Q>
                </Card>
              </div>
            </Section>

            <Section title={t("sec.where")} desc={t("sec.where_desc")}>
              <div className="grid">
                <Card icon="pie" title={t("card.classes")} sub={t("card.classes_sub", { scope: o.scope_label })}>
                  <div className="band-cuts">
                    <label className="field">{t("chart.class_min")}
                      <input type="number" min={0} step={10000} value={classMin} onChange={(e) => setClassMin(e.target.value)} />
                    </label>
                    <label className="field">{t("chart.class_max")}
                      <input type="number" min={0} step={10000} value={classMax} onChange={(e) => setClassMax(e.target.value)} />
                    </label>
                  </div>
                  <p className="muted small">{rangeOk ? t("chart.class_span") : t("chart.class_order")}</p>
                  {(() => {
                    const compared = classes.data ?? o.class_compare;
                    if (!compared.labels.length) return <p className="muted">{t("chart.class_empty")}</p>;
                    return (
                      <>
                        <Chart option={classCompareOption(compared, fmt)} label={t("chart.classes_aria")} exportName={t("card.classes")} height={360} />
                        <div className="scroll">
                          <table className="t">
                            <thead>
                              <tr>
                                <th>{t("col.year")}</th>
                                {compared.labels.map((label) => <th key={label} className="r">{label}</th>)}
                                <th className="r">{t("col.total")}</th>
                              </tr>
                            </thead>
                            <tbody>
                              {compared.series.map((row) => (
                                <tr key={row.year}>
                                  <td>{row.year}</td>
                                  {row.amounts.map((amount, index) => <td key={compared.labels[index]} className="r num">{fmt.axisMoney(amount)}</td>)}
                                  <td className="r num">{fmt.axisMoney(row.amounts.reduce((sum, amount) => sum + amount, 0))}</td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>
                      </>
                    );
                  })()}
                </Card>
              </div>
              <div className="grid">
                <Card icon="pie" title={t("card.directed")} sub={t("card.directed_sub", { scope: t("scope.ordinary") })}>
                  <Q q={tree}>{(tr) => <PurposeBoard tree={tr} label={t("chart.tree_aria")} />}</Q>
                </Card>
              </div>
              <div className="grid g2">
                <Card icon="data" title={t("card.methods")} sub={o.scope_label}>
                  {o.methods.length ? <Chart option={donutOption(o.methods.filter((m) => m.amount != null), fmt)} label={t("chart.methods_aria")} exportName={t("card.methods")} height={270} /> : (
                    <Notice tone="block" title={t("overview.methods_missing_title")}>{t("overview.methods_missing")}</Notice>
                  )}
                </Card>
                <Card icon="data" title={t("card.colleges")} sub={t("card.colleges_sub")}>
                  {o.colleges.length ? <Chart option={hbar(o.colleges, fmt)} label={t("chart.colleges_aria")} exportName={t("card.colleges")} height={270} /> : <p className="muted">{t("overview.no_colleges")}</p>}
                </Card>
              </div>
            </Section>

            <Section id="when" title={t("sec.when")} desc={t("sec.when_desc")}>
              <div className="grid g2">
                <Card icon="calendar" title={t("chart.season_title")} sub={t("chart.season_sub")}>
                  <Q q={season}>{(s) => <Chart option={heatmapOption(s, fmt)} label={t("chart.season_aria")} exportName={t("chart.season_title")} height={110 + 56 * s.years.length} />}</Q>
                  <div className="how">{t("how.season")}</div>
                </Card>
                <Card icon="calendar" title={t("chart.monthly_title", { year: o.year })} sub={o.scope_label}
                  right={<label className="small muted"><input type="checkbox" checked={log} onChange={(e) => setLog(e.target.checked)} /> {t("chart.log")}</label>}>
                  <Chart option={monthlyOption(o.monthly, log, fmt, t)} label={t("chart.monthly_aria")} exportName={t("chart.monthly_title", { year: o.year })} height={300} />
                </Card>
              </div>
            </Section>

            <Section id="concentration" title={t("sec.conc")} desc={t("sec.conc_desc")}>
              <Q q={conc}>{(c) => (
                <div className="grid g-main">
                  <Card icon="pie" title={t("chart.conc_title")} sub={t("chart.conc_sub")} help="tip.conc">
                    <Chart option={concentrationOption(c, t)} label={t("chart.conc_aria")} exportName={t("chart.conc_title")} height={330} />
                    <div className="how">{t("how.conc")}</div>
                  </Card>
                  <div className="stack">
                    <div className="kpi warn"><div className="l">{t("conc.top1_all")}</div><div className="v">{fmt.pct(c.all.top1pct_share, 0)}</div><div className="s">{t("conc.donors_n", { n: Math.max(1, Math.ceil(c.all.n_donors / 100)) })}</div></div>
                    <div className="kpi accent"><div className="l">{t("conc.top1_ord")}</div><div className="v">{fmt.pct(c.ordinary.top1pct_share, 0)}</div><div className="s">{t("conc.donors_n", { n: Math.max(1, Math.ceil(c.ordinary.n_donors / 100)) })}</div></div>
                    <div className="kpi"><div className="l">{t("conc.top10_all")}</div><div className="v">{fmt.pct(c.all.top10pct_share, 0)}</div><div className="s">{t("conc.top10_ord", { pct: fmt.pct(c.ordinary.top10pct_share, 0) })}</div></div>
                  </div>
                </div>
              )}</Q>
            </Section>

            <Accordion title={t("sec.tables")} open={tablesOpen} onToggle={(open) => { if (!holdToggle.current) setTablesOpen(open); }}>
              <div className="grid g2">
                <div><h3 style={{ marginBottom: 8 }}>{t("card.bands")}</h3><Chart option={hbar(o.bands, fmt)} label={t("chart.bands_aria")} exportName={t("card.bands")} height={230} /><BreakdownTable rows={o.bands} first={t("col.band")} /></div>
                <div><h3 style={{ marginBottom: 8 }}>{t("card.classes")}</h3><BreakdownTable rows={o.donor_classes} first={t("col.category")} /></div>
              </div>
              <div className="grid g2">
                <div><h3 style={{ marginBottom: 8 }}>{t("card.directed")}</h3><BreakdownTable rows={o.purpose_groups} first={t("col.purpose")} />
                  <h3 style={{ margin: "14px 0 6px" }}>{t("card.designated")}</h3><BreakdownTable rows={o.purpose_subs} first={t("col.category")} /></div>
                <div><h3 style={{ marginBottom: 8 }}>{t("card.methods")}</h3>{o.methods.length ? <BreakdownTable rows={o.methods} first={t("col.method")} /> : <p className="muted">{t("overview.methods_missing")}</p>}
                  <h3 style={{ margin: "14px 0 6px" }}>{t("card.over1m")}</h3>
                  {o.projects_over_1m.length ? (
                    <table className="t"><thead><tr><th>{t("col.project")}</th><th className="r">{t("col.amount")}</th></tr></thead>
                      <tbody>{o.projects_over_1m.map((p) => <tr key={p.project}><td>{p.project}</td><td className="r num">{fmt.ntd(p.amount)}</td></tr>)}</tbody></table>
                  ) : <p className="muted">{t("overview.none_here")}</p>}</div>
              </div>
            </Accordion>
            {o.notes.length > 0 && (
              <Notice tone="warn" title={t("overview.notes_title")}>
                <ul>{o.notes.map((n) => <li key={n}>{n}</li>)}</ul>
              </Notice>
            )}
          </>
        );
      }}</Q>
    </>
  );
}
