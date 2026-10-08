import { useEffect, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { useBridge, useConcentration, useHighlights, useOverview, usePurposeTree, useSeasonality, useTrend } from "../api/hooks";
import type { Breakdown } from "../api/types";
import { AiSummary } from "../components/AiParts";
import { Chart } from "../components/Chart";
import { Accordion, Bar, Card, Icon, Notice, PageHeader, Q, Section, Seg, StatCard, type IconName } from "../components/ui";
import { useApp } from "../context/AppContext";
import { useI18n } from "../i18n";
import type { Key } from "../i18n/en";
import { bubbleOption as _unused, comboOption, concentrationOption, donutOption, hbar, heatmapOption, monthlyOption, treemapOption, waterfallOption } from "../lib/options";

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

export default function Overview() {
  const { datasetId, settings } = useApp();
  const { t, tx, fmt } = useI18n();
  const loc = useLocation();
  const signed = signedWith(fmt.compact);
  const [year, setYear] = useState<number | undefined>();
  const [scope, setScope] = useState<"all" | "regular">("all");
  const [log, setLog] = useState(false);
  const [mode, setMode] = useState<"ordinary" | "all">("ordinary");
  const trend = useTrend(datasetId, settings.exceptional);
  const ov = useOverview(datasetId, { year, scope, exceptional: settings.exceptional, large: settings.large, returnDef: settings.returnDef });
  const y = ov.data?.year;
  const hl = useHighlights(datasetId, y, settings.exceptional);
  const bridge = useBridge(datasetId, y, settings.exceptional);
  const conc = useConcentration(datasetId, y, settings.exceptional);
  const season = useSeasonality(datasetId, settings.exceptional);
  const tree = usePurposeTree(datasetId, y, settings.exceptional);

  // links such as "/#concentration" scroll to their section once the page has drawn
  useEffect(() => {
    if (loc.hash && ov.data) setTimeout(() => document.querySelector(loc.hash)?.scrollIntoView({ behavior: "smooth", block: "start" }), 250);
  }, [loc.hash, ov.data]);

  return (
    <>
      <PageHeader title={t("overview.title")} question={t("q.overview")} desc={t("overview.desc")}>
        <label className="field">{t("overview.year")}
          <select value={y ?? ""} onChange={(e) => setYear(Number(e.target.value))}>
            {(ov.data?.years ?? []).map((v) => <option key={v}>{v}</option>)}
          </select>
        </label>
        <div className="field">{t("overview.scope")}
          <Seg label={t("overview.scope")} value={scope} onChange={setScope} options={[{ v: "all", l: t("scope.all") }, { v: "regular", l: t("scope.regular") }]} />
        </div>
      </PageHeader>
      <Q q={ov}>{(o) => {
        const k = o.kpis;
        const rows = trend.data ?? [];
        const spark = (f: (r: (typeof rows)[number]) => number) => rows.map(f);
        const vs = t("kpi.vs", { year: o.prev_year ?? "–" });
        return (
          <>
            <div className="hero rise">
              <div className="eyebrow">{t("hero.eyebrow", { year: o.year })}</div>
              <p className="headline">{o.prev_year != null && k.regular_yoy_pct != null
                ? tx("hero.sentence", { year: o.year, total: fmt.compact(k.total), ordinary: fmt.compact(k.regular_total), change: fmt.signedPct(k.regular_yoy_pct) })
                : tx("hero.sentence_first", { year: o.year, total: fmt.compact(k.total), ordinary: fmt.compact(k.regular_total) })}</p>
              <div className="hero-stats">
                <div className="hero-stat"><div className="l">{t("kpi.total", { year: o.year })}</div><div className="v">{fmt.compact(k.total)}</div><div className="d">{k.total_yoy_pct != null ? `${fmt.signedPct(k.total_yoy_pct)} ${vs}` : " "}</div></div>
                <div className="hero-stat"><div className="l">{t("kpi.ordinary")}</div><div className="v">{fmt.compact(k.regular_total)}</div><div className="d">{k.regular_yoy_pct != null ? `${fmt.signedPct(k.regular_yoy_pct)} ${vs}` : " "}</div></div>
                <div className="hero-stat"><div className="l">{t("kpi.donors")}</div><div className="v">{fmt.int(k.donors)}</div><div className="d">{t("kpi.donors_sub", { records: fmt.int(k.records), inkind: k.in_kind_records })}</div></div>
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
              <div className="stats">
                <StatCard icon="money" label={t("kpi.total", { year: o.year })} value={fmt.compact(k.total)} spark={spark((r) => r.total)} help="tip.total"
                  sub={<><span className={`delta ${(k.total_yoy_pct ?? 0) >= 0 ? "up" : "down"}`}>{fmt.signedPct(k.total_yoy_pct)}</span> {vs}</>} />
                <StatCard icon="trend" label={t("kpi.ordinary")} value={fmt.compact(k.regular_total)} spark={spark((r) => r.regular)} help="tip.ordinary"
                  sub={<><span className={`delta ${(k.regular_yoy_pct ?? 0) >= 0 ? "up" : "down"}`}>{fmt.signedPct(k.regular_yoy_pct)}</span> {vs}</>} />
                <StatCard icon="gift" tone="amber" label={t("kpi.exceptional")} value={fmt.compact(k.exceptional_total)} help="tip.exceptional"
                  sub={t("kpi.exceptional_sub", { n: k.n_exceptional, pct: fmt.pct(k.share_exceptional, 0) })} />
                <StatCard icon="people" tone="indigo" label={t("kpi.donors")} value={fmt.int(k.donors)} spark={spark((r) => r.donors)}
                  sub={t("kpi.donors_sub", { records: fmt.int(k.records), inkind: k.in_kind_records })} />
                <StatCard icon="repeat" tone="indigo" label={t("kpi.repeat")} value={fmt.int(k.repeat_selected)} help="tip.repeat" sub={t(`return.${settings.returnDef}` as Key)} />
                <StatCard icon="calendar" label={t("kpi.large", { threshold: fmt.compact(settings.large) })} value={fmt.int(k.large_gifts)} sub={fmt.compact(k.large_gifts_amount)} />
              </div>
            </Section>

            <Section title={t("sec.change")} desc={t("sec.change_desc")}>
              <div className="grid" style={{ gridTemplateColumns: "repeat(auto-fit, minmax(min(100%, 380px), 1fr))" }}>
                <Card icon="trend" title={t("chart.total_title")} sub={t("chart.total_sub")}>
                  <Q q={trend}>{(r) => <Chart option={comboOption(r, fmt, t)} label={t("chart.total_aria")} height={310} />}</Q>
                  <div className="how">{t("how.combo")}</div>
                </Card>
                <Card icon="chart" title={t("chart.bridge_title")} sub={t("chart.bridge_sub", { year: o.year })} help="tip.bridge"
                  right={<Seg label={t("chart.bridge_mode")} value={mode} onChange={setMode} options={[{ v: "ordinary", l: t("scope.ordinary") }, { v: "all", l: t("scope.all") }]} />}>
                  <Q q={bridge}>{(b) => (
                    <>
                      <Chart option={waterfallOption(b, mode, fmt, t)} label={t("chart.bridge_aria")} height={310} />
                      {mode === "ordinary" && <div className="how">{t("how.bridge_exc", { change: signed(b.exceptional_end - b.exceptional_start) })}</div>}
                    </>
                  )}</Q>
                </Card>
              </div>
            </Section>

            <Section title={t("sec.where")} desc={t("sec.where_desc")}>
              <div className="grid g2">
                <Card icon="pie" title={t("card.classes")} sub={o.scope_label}>
                  <Chart option={donutOption(o.donor_classes, fmt)} label={t("chart.classes_aria")} height={290} />
                </Card>
                <Card icon="pie" title={t("card.directed")} sub={t("card.directed_sub", { scope: t("scope.ordinary") })}>
                  <Q q={tree}>{(tr) => <Chart option={treemapOption(tr, fmt)} label={t("chart.tree_aria")} height={290} />}</Q>
                </Card>
              </div>
              <div className="grid g2">
                <Card icon="data" title={t("card.methods")} sub={o.scope_label}>
                  {o.methods.length ? <Chart option={donutOption(o.methods.filter((m) => m.amount != null), fmt)} label={t("chart.methods_aria")} height={270} /> : (
                    <Notice tone="block" title={t("overview.methods_missing_title")}>{t("overview.methods_missing")}</Notice>
                  )}
                </Card>
                <Card icon="data" title={t("card.colleges")} sub={t("card.colleges_sub")}>
                  {o.colleges.length ? <Chart option={hbar(o.colleges, fmt)} label={t("chart.colleges_aria")} height={270} /> : <p className="muted">{t("overview.no_colleges")}</p>}
                </Card>
              </div>
            </Section>

            <Section id="when" title={t("sec.when")} desc={t("sec.when_desc")}>
              <div className="grid g2">
                <Card icon="calendar" title={t("chart.season_title")} sub={t("chart.season_sub")}>
                  <Q q={season}>{(s) => <Chart option={heatmapOption(s, fmt)} label={t("chart.season_aria")} height={110 + 56 * s.years.length} />}</Q>
                  <div className="how">{t("how.season")}</div>
                </Card>
                <Card icon="calendar" title={t("chart.monthly_title", { year: o.year })} sub={o.scope_label}
                  right={<label className="small muted"><input type="checkbox" checked={log} onChange={(e) => setLog(e.target.checked)} /> {t("chart.log")}</label>}>
                  <Chart option={monthlyOption(o.monthly, log, fmt, t)} label={t("chart.monthly_aria")} height={300} />
                </Card>
              </div>
            </Section>

            <Section id="concentration" title={t("sec.conc")} desc={t("sec.conc_desc")}>
              <Q q={conc}>{(c) => (
                <div className="grid g-main">
                  <Card icon="pie" title={t("chart.conc_title")} sub={t("chart.conc_sub")} help="tip.conc">
                    <Chart option={concentrationOption(c, t)} label={t("chart.conc_aria")} height={330} />
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

            <Accordion title={t("sec.tables")}>
              <div className="grid g2">
                <div><h3 style={{ marginBottom: 8 }}>{t("card.bands")}</h3><Chart option={hbar(o.bands, fmt)} label={t("chart.bands_aria")} height={230} /><BreakdownTable rows={o.bands} first={t("col.band")} /></div>
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
