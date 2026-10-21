import type { Bridge, Breakdown, Concentration, Highlight, Overview, TrendRow, TreeNode } from "../api/types";
import type { Fmt } from "../i18n";
import type { Key } from "../i18n/en";
import type { CsvCell } from "./download";
import { purposeBlocks } from "./purpose";

type T = (key: Key, params?: Record<string, string | number>) => string;

const plain = (text: string) => text.replace(/<\/?b>/g, "");
const dollars = (n: number | null | undefined): CsvCell => (n == null ? "" : Math.round(n));
/** Year-on-year figures are already percentages, for example -64.7. Shares are fractions. */
const points = (n: number | null | undefined): CsvCell => (n == null ? "" : Math.round(n * 10) / 10);
const sharePct = (fraction: number | null | undefined): CsvCell => (fraction == null ? "" : Math.round(fraction * 1000) / 10);

export function buildOverviewExport(input: {
  t: T;
  fmt: Fmt;
  overview: Overview;
  trend: TrendRow[];
  highlights: Highlight[];
  bridge?: Bridge;
  concentration?: Concentration;
  tree?: TreeNode[];
  bands?: { low: number; high: number };
  classCompare?: Overview["class_compare"];
  returnLabel: string;
  exceptional: number;
  large: number;
}): { summary: string; tables: CsvCell[][] } {
  const { t, fmt, overview: o, trend, highlights, bridge, concentration, tree, bands, classCompare, returnLabel, exceptional, large } = input;
  const k = o.kpis;
  const vs = o.prev_year != null ? t("kpi.vs", { year: o.prev_year }) : "";
  const share = t("export.col_share_pct");
  const amount = t("col.amount");
  const gifts = t("col.gifts");

  const lines = [
    plain(t("hero.eyebrow", { year: o.year })),
    "",
    plain(o.prev_year != null && k.regular_yoy_pct != null
      ? t("hero.sentence", { year: o.year, compare: o.prev_year, total: fmt.compact(k.total), ordinary: fmt.compact(k.regular_total), change: fmt.signedPct(k.regular_yoy_pct) })
      : t("hero.sentence_first", { year: o.year, total: fmt.compact(k.total), ordinary: fmt.compact(k.regular_total) })),
    "",
    t("export.scope_line", { scope: o.scope_label }),
    t("export.threshold_exc", { amount: fmt.compact(exceptional) }),
    t("export.threshold_large", { amount: fmt.compact(large) }),
    t("export.repeat_rule", { rule: returnLabel }),
    "",
    t("sec.numbers"),
    line(t("kpi.total", { year: o.year }), fmt.ntd(k.total), k.total_yoy_pct, vs),
    line(t("kpi.ordinary"), fmt.ntd(k.regular_total), k.regular_yoy_pct, vs),
    line(t("kpi.exceptional"), `${fmt.ntd(k.exceptional_total)} · ${t("kpi.exceptional_sub", { n: k.n_exceptional, pct: fmt.pct(k.share_exceptional, 0) })}`),
    line(t("kpi.donors"), `${fmt.int(k.donors)} · ${t("kpi.donors_sub", { records: fmt.int(k.records), inkind: k.in_kind_records })}`),
    line(t("kpi.repeat"), k.repeat_selected == null ? t("ui.na") : fmt.int(k.repeat_selected)),
    line(t("kpi.large", { threshold: fmt.compact(large) }), `${fmt.int(k.large_gifts)} · ${fmt.ntd(k.large_gifts_amount)}`),
    line(t("kpi.repeat_hero"), k.repeat_selected == null ? t("ui.na") : `${fmt.int(k.repeat_selected)}${k.repeat_delta == null ? "" : ` (${k.repeat_delta >= 0 ? "+" : ""}${k.repeat_delta})`}`),
    line(t("kpi.card"), k.card_gifts == null ? t("kpi.card_missing") : String(k.card_gifts), k.card_yoy_pct, vs),
    line(t("kpi.million"), `${fmt.pct(k.million_share, 0)} · ${t("kpi.million_sub", { count: k.million_projects, amount: fmt.ntd(k.million_amount) })}`),
    line(t("kpi.acct_income"), t("kpi.acct_missing")),
    line(t("kpi.acct_balance"), t("kpi.acct_missing")),
  ];

  if (highlights.length) {
    lines.push("", t("sec.next"));
    for (const card of highlights) lines.push(`- ${card.title}`, `  ${card.text}`);
  }
  if (bridge) {
    lines.push("", t("chart.bridge_title"));
    lines.push(`- ${t("bridge.start", { year: bridge.prev_year })}: ${fmt.ntd(bridge.start)}`);
    for (const step of bridge.steps) {
      const donors = step.donors == null ? "" : ` (${t("bridge.donors", { n: step.donors })})`;
      lines.push(`- ${step.label}: ${signed(fmt.ntd, step.value)}${donors}`);
    }
    lines.push(`- ${t("bridge.end", { year: bridge.year })}: ${fmt.ntd(bridge.end)}`);
  }
  if (concentration) {
    lines.push("", t("chart.conc_title"));
    lines.push(`- ${t("conc.top1_all")}: ${fmt.pct(concentration.all.top1pct_share, 0)} (${t("conc.donors_n", { n: Math.max(1, Math.ceil(concentration.all.n_donors / 100)) })})`);
    lines.push(`- ${t("conc.top1_ord")}: ${fmt.pct(concentration.ordinary.top1pct_share, 0)}`);
    lines.push(`- ${t("conc.top10_all")}: ${fmt.pct(concentration.all.top10pct_share, 0)}`);
    lines.push(`- ${t("conc.ordinary")}: ${fmt.pct(concentration.ordinary.top10pct_share, 0)}`);
  }
  if (o.notes.length) {
    lines.push("", t("overview.notes_title"));
    for (const note of o.notes) lines.push(`- ${note}`);
  }
  lines.push("", t("export.readme"));

  const tables: CsvCell[][] = [
    [t("sec.numbers")],
    [t("export.metric"), t("export.value"), t("export.col_change_pct")],
    [t("kpi.total", { year: o.year }), dollars(k.total), points(k.total_yoy_pct)],
    [t("kpi.ordinary"), dollars(k.regular_total), points(k.regular_yoy_pct)],
    [t("kpi.exceptional"), dollars(k.exceptional_total), sharePct(k.share_exceptional)],
    [t("kpi.donors"), k.donors, ""],
    [t("col.gifts"), k.records, ""],
    [t("kpi.repeat"), k.repeat_selected ?? "", ""],
    [t("kpi.large", { threshold: fmt.compact(large) }), k.large_gifts, ""],
    [],
    [t("chart.kpi_title")],
    [t("col.year"), t("kpi.total_axis"), t("kpi.ordinary"), t("kpi.exceptional"), t("kpi.donors"), t("kpi.repeat"), t("kpi.large_count"), t("kpi.large_amount"), t("kpi.card_amount"), t("kpi.card")],
    ...o.kpi_compare.map((row) => [row.year, dollars(row.total), dollars(row.regular_total), dollars(row.exceptional_total), row.donors, row.repeat ?? "", row.large_gifts, dollars(row.large_gifts_amount), dollars(row.card_amount), row.card_gifts ?? ""]),
    [],
    [t("chart.total_title")],
    [t("col.year"), amount,
      bands ? t("series.band_under", { amount: fmt.compact(bands.low) }) : t("series.ordinary"),
      bands ? t("series.band_mid", { low: fmt.compact(bands.low), high: fmt.compact(bands.high) }) : t("series.exceptional"),
      bands ? t("series.band_over", { amount: fmt.compact(bands.high) }) : "",
      t("series.ordinary"), t("series.exceptional"), t("series.donors"), gifts, t("export.col_change_pct")],
    ...trend.map((row) => [row.year, dollars(row.total), dollars(row.band_under), dollars(row.band_mid), dollars(row.band_over), dollars(row.regular), dollars(row.exceptional), row.donors, row.records, points(row.total_yoy_pct)]),
    [],
    [t("chart.monthly_title", { year: o.year })],
    [t("export.month"), amount, t("series.ordinary"), t("series.exceptional"), gifts],
    ...o.monthly.map((row) => [fmt.month(row.month), dollars(row.total), dollars(row.regular), dollars(row.exceptional), row.records]),
    [],
  ];
  const block = (title: string, first: string, rows: Breakdown[]) => {
    tables.push(
      [title],
      [first, amount, gifts, share],
      ...rows.map((row) => [row.label, dollars(row.amount), row.count, sharePct(row.share_amount)]),
      [],
    );
  };
  block(t("card.bands"), t("col.band"), o.bands);
  block(t("card.classes"), t("col.category"), o.donor_classes);
  const compared = classCompare ?? o.class_compare;
  if (compared.series.length) {
    tables.push(
      [t("card.classes")],
      [t("col.year"), ...compared.labels, t("col.total")],
      ...compared.series.map((row) => [row.year, ...row.amounts.map((amount) => dollars(amount)), dollars(row.amounts.reduce((sum, amount) => sum + amount, 0))]),
      [],
    );
  }
  block(t("card.methods"), t("col.method"), o.methods);
  block(t("card.directed"), t("col.purpose"), o.purpose_groups);
  block(t("card.designated"), t("col.category"), o.purpose_subs);
  if (tree?.length) {
    tables.push(
      [t("card.directed")],
      [t("col.purpose"), t("col.category"), t("col.band"), t("col.project"), amount],
      ...purposeBlocks(tree).flatMap((block) => block.sections.flatMap((section) => section.bands.flatMap((band) => band.projects.map((project) => [
        block.name, section.name === block.name ? "" : section.name, t(band.key), project.name, dollars(project.value),
      ])))),
      [],
    );
  }
  block(t("card.colleges"), t("col.category"), o.colleges);
  tables.push(
    [t("card.over1m")],
    [t("col.project"), amount],
    ...o.projects_over_1m.map((row) => [row.project, dollars(row.amount)]),
    [],
  );
  if (bridge) {
    tables.push(
      [t("chart.bridge_title")],
      [t("export.metric"), t("export.change_ntd"), t("col.donor")],
      [t("bridge.start", { year: bridge.prev_year }), dollars(bridge.start), ""],
      ...bridge.steps.map((step) => [step.label, dollars(step.value), step.donors ?? ""]),
      [t("bridge.end", { year: bridge.year }), dollars(bridge.end), ""],
      [],
    );
  }
  if (concentration) {
    tables.push(
      [t("chart.conc_title")],
      [t("export.metric"), share],
      [`${t("conc.all")} · ${t("conc.top1_all")}`, sharePct(concentration.all.top1pct_share)],
      [`${t("conc.ordinary")} · ${t("conc.top1_all")}`, sharePct(concentration.ordinary.top1pct_share)],
      [`${t("conc.all")} · ${t("conc.top10_all")}`, sharePct(concentration.all.top10pct_share)],
      [`${t("conc.ordinary")} · ${t("conc.top10_all")}`, sharePct(concentration.ordinary.top10pct_share)],
      [],
    );
  }
  return { summary: `${lines.join("\n")}\n`, tables };
}

function line(label: string, value: string, change?: number | null, vs?: string): string {
  const delta = change == null || !vs ? "" : ` (${change >= 0 ? "+" : ""}${change.toFixed(1)}% ${vs})`;
  return `- ${label}: ${value}${delta}`;
}

function signed(ntd: Fmt["ntd"], value: number): string {
  return `${value < 0 ? "−" : "+"}${ntd(Math.abs(value))}`;
}
