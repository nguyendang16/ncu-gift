/** Chart option builders. Each takes the active language's formatters so every label, axis and tooltip follows it. */
import type { Bridge, Breakdown, Concentration, Journey, RiskPoint, Scenario, Season, TrendRow } from "../api/types";
import type { Fmt } from "../i18n";
import type { Key } from "../i18n/en";
import { C, PALETTE, axisText, baseOption, yMoney } from "./chart";

export type T = (key: Key, params?: Record<string, string | number>) => string;
const tip = (fmt: Fmt) => ({ valueFormatter: (v: number) => fmt.ntd(v) });

/** One value per bar, written upward so neighbouring years do not sit on the same line. */
function columnLabel(format: (v: number) => string) {
  return {
    show: true, position: "top" as const, rotate: 90, align: "left" as const, verticalAlign: "middle" as const,
    distance: 4, color: C.ink, fontSize: 11,
    formatter: (p: { value: number | null }) => (p.value ? format(p.value) : ""),
  };
}

/** Round the axis above the tallest bar so its upward label stays inside, on a clean tick. */
function withHeadroom<T extends object>(axis: T, peak: number) {
  if (peak <= 0) return axis;
  const target = peak * 1.28;
  const exp = Math.floor(Math.log10(target));
  const frac = target / 10 ** exp;
  const step = [1, 2, 2.5, 4, 5, 10].find((s) => s >= frac) ?? 10;
  return { ...axis, max: step * 10 ** exp };
}

/** Ordinary and exceptional giving stacked, with the number of donors as a line on its own axis. */
export function comboOption(rows: TrendRow[], cuts: { low: number; high: number }, fmt: Fmt, t: T) {
  const b = baseOption();
  const under = t("series.band_under", { amount: fmt.compact(cuts.low) });
  const mid = t("series.band_mid", { low: fmt.compact(cuts.low), high: fmt.compact(cuts.high) });
  const over = t("series.band_over", { amount: fmt.compact(cuts.high) });
  const share = (value: number, total: number) => (total > 0 ? Math.round(value / total * 100) : 0);
  const peak = Math.max(...rows.map((r) => r.total), 1);
  const inside = (color: string) => ({
    show: true, color, fontSize: 11, fontWeight: 650,
    formatter: (p: { dataIndex: number; value: number }) => {
      const total = rows[p.dataIndex]?.total ?? 0;
      const room = p.value / peak;
      if (!p.value || !total || room < 0.14) return "";
      return room < 0.28 ? fmt.axisMoney(p.value) : `${fmt.axisMoney(p.value)}\n${share(p.value, total)}%`;
    },
  });
  const band = (name: string, key: "band_under" | "band_mid" | "band_over", color: string, label: string, radius: number[]) => ({
    name, type: "bar" as const, stack: "t", barMaxWidth: 72,
    data: rows.map((r) => (r[key] > 0 ? r[key] : null)),
    itemStyle: { color, borderRadius: radius },
    label: inside(label),
  });
  return {
    ...b, tooltip: { ...b.tooltip, ...tip(fmt) },
    grid: { left: 6, right: 48, top: 28, bottom: 52, containLabel: true },
    legend: { bottom: 0, left: "center", icon: "roundRect" as const, itemWidth: 12, itemHeight: 12, textStyle: { color: C.muted, fontSize: 12 }, data: [under, mid, over, t("series.donors")] },
    xAxis: { type: "category" as const, data: rows.map((r) => String(r.year)), axisLabel: axisText },
    yAxis: [withHeadroom(yMoney(fmt.axisMoney), peak), { type: "value" as const, axisLabel: axisText, splitLine: { show: false }, name: "", min: 0 }],
    series: [
      band(under, "band_under", "#4c1d95", "#fff", [0, 0, 0, 0]),
      band(mid, "band_mid", "#9333ea", "#fff", [0, 0, 0, 0]),
      band(over, "band_over", "#d4a017", "#3f2d00", [6, 6, 0, 0]),
      { name: "total", type: "bar" as const, stack: "t", data: rows.map(() => 0), tooltip: { show: false },
        itemStyle: { color: "transparent" }, emphasis: { disabled: true },
        label: { show: true, position: "top" as const, distance: 6, color: C.ink, fontWeight: 650, fontSize: 12, formatter: (p: { dataIndex: number }) => fmt.axisMoney(rows[p.dataIndex]?.total ?? 0) } },
      { name: t("series.donors"), type: "line" as const, yAxisIndex: 1, data: rows.map((r) => r.donors), symbol: "circle", symbolSize: 9, lineStyle: { width: 3, color: C.indigo }, itemStyle: { color: C.indigo },
        tooltip: { valueFormatter: (v: number) => fmt.int(v) } },
    ],
  };
}

/** Why did giving change? Start, then the effect of each group of donors, then the end. Adds up exactly. */
export function waterfallOption(b: Bridge, mode: "ordinary" | "all", fmt: Fmt, t: T) {
  const steps = mode === "ordinary" ? b.steps.filter((s) => s.key !== "exceptional") : b.steps;
  const start = mode === "ordinary" ? b.start_ordinary : b.start;
  const end = mode === "ordinary" ? b.end_ordinary : b.end;
  const labels = [t("bridge.start", { year: b.prev_year }), ...steps.map((s) => s.label), t("bridge.end", { year: b.year })];
  const base: number[] = [0], up: (number | null)[] = [null], down: (number | null)[] = [null], total: (number | null)[] = [start];
  let run = start;
  for (const s of steps) {
    if (s.value >= 0) { base.push(run); up.push(s.value); down.push(null); } else { base.push(run + s.value); up.push(null); down.push(-s.value); }
    total.push(null);
    run += s.value;
  }
  base.push(0); up.push(null); down.push(null); total.push(end);
  const bar = (name: string, data: (number | null)[], color: string, signed = 0) => ({
    name, type: "bar" as const, stack: "w", data, itemStyle: { color, borderRadius: 4 }, barMaxWidth: 54,
    label: { show: true, position: "top" as const, color: C.ink, fontSize: 12, formatter: (p: { value: number }) => (p.value == null ? "" : (signed > 0 ? "+" : signed < 0 ? "−" : "") + fmt.compact(p.value)) },
  });
  const b0 = baseOption();
  return {
    ...b0, legend: undefined, tooltip: { ...b0.tooltip, formatter: (p: unknown) => {
      const i = (p as { dataIndex: number }[])[0].dataIndex;
      if (i === 0) return `${labels[0]}<br/><b>${fmt.ntd(start)}</b>`;
      if (i === labels.length - 1) return `${labels[i]}<br/><b>${fmt.ntd(end)}</b>`;
      const s = steps[i - 1];
      return `${s.label}<br/><b>${s.value >= 0 ? "+" : "−"}${fmt.ntd(Math.abs(s.value))}</b>${s.donors != null ? `<br/>${t("bridge.donors", { n: s.donors })}` : ""}`;
    } },
    xAxis: { type: "category" as const, data: labels, axisLabel: { ...axisText, fontSize: 11, interval: 0, width: 62, overflow: "break" as const } },
    yAxis: yMoney(fmt.axisMoney),
    series: [
      { name: "base", type: "bar" as const, stack: "w", data: base, itemStyle: { color: "transparent" }, silent: true, tooltip: { show: false } },
      bar("total", total, C.slate), bar("up", up, C.green, 1), bar("down", down, C.rose, -1),
    ],
  };
}

export function kpiCompareOption(labels: string[], series: { year: number; values: (number | null)[] }[], fmt: Fmt, money: boolean) {
  const b = baseOption();
  const colors = [C.violet, C.indigo, C.regular, C.sky, C.exceptional];
  const format = (v: number) => (money ? fmt.axisMoney(v) : fmt.int(v));
  const peak = Math.max(0, ...series.flatMap((row) => row.values.map((v) => v ?? 0)));
  return {
    ...b,
    tooltip: { ...b.tooltip, valueFormatter: (v: number) => (v == null ? "–" : money ? fmt.ntd(v) : fmt.int(v)) },
    grid: { left: 8, right: 16, top: 16, bottom: 36, containLabel: true },
    legend: { bottom: 0, left: "center", icon: "roundRect" as const, itemWidth: 12, itemHeight: 12, textStyle: { color: C.muted, fontSize: 12 } },
    xAxis: { type: "category" as const, data: labels, axisLabel: { ...axisText, interval: 0, hideOverlap: true } },
    yAxis: withHeadroom(money ? yMoney(fmt.axisMoney) : { type: "value" as const, min: 0, axisLabel: { ...axisText, hideOverlap: true, formatter: (v: number) => fmt.int(v) }, splitLine: { lineStyle: { color: C.line, type: "dashed" as const } } }, peak),
    series: series.map((row, index) => ({
      name: String(row.year), type: "bar" as const, data: row.values, barMaxWidth: 22, barGap: "30%",
      itemStyle: { color: colors[index % colors.length], borderRadius: [4, 4, 0, 0] },
      label: columnLabel((v) => (v ? format(v) : "")),
      labelLayout: { hideOverlap: true },
    })),
  };
}

export function classCompareOption(compare: { labels: string[]; series: { year: number; amounts: number[] }[] }, fmt: Fmt) {
  const b = baseOption();
  const colors = [C.violet, C.indigo, C.regular, C.sky, C.exceptional];
  const peak = Math.max(0, ...compare.series.flatMap((row) => row.amounts));
  return {
    ...b,
    tooltip: { ...b.tooltip, ...tip(fmt) },
    grid: { left: 8, right: 16, top: 16, bottom: 36, containLabel: true },
    legend: { bottom: 0, left: "center", icon: "roundRect" as const, itemWidth: 12, itemHeight: 12, textStyle: { color: C.muted, fontSize: 12 } },
    xAxis: { type: "category" as const, data: compare.labels, axisLabel: { ...axisText, interval: 0, width: 72, overflow: "break" as const, hideOverlap: true } },
    yAxis: withHeadroom(yMoney(fmt.axisMoney), peak),
    series: compare.series.map((row, index) => ({
      name: String(row.year), type: "bar" as const, data: row.amounts, barMaxWidth: 22, barGap: "30%",
      itemStyle: { color: colors[index % colors.length], borderRadius: [4, 4, 0, 0] },
      label: columnLabel((v) => (v ? fmt.axisMoney(v) : "")),
      labelLayout: { hideOverlap: true },
    })),
  };
}

export function donutOption(rows: Breakdown[], fmt: Fmt) {
  const data = rows.filter((r) => (r.amount ?? 0) > 0).map((r) => ({ name: r.label, value: r.amount as number }));
  return {
    animation: false, color: PALETTE, textStyle: { fontFamily: "inherit" },
    tooltip: { trigger: "item" as const, confine: true, formatter: (p: { name: string; value: number; percent: number }) => `${p.name}<br/><b>${fmt.ntd(p.value)}</b> · ${p.percent}%` },
    series: [{ type: "pie" as const, radius: ["46%", "70%"], center: ["50%", "50%"], data, avoidLabelOverlap: true,
      itemStyle: { borderColor: "#fff", borderWidth: 3, borderRadius: 6 }, label: { color: C.ink, fontSize: 12, formatter: "{b}\n{d}%" }, labelLine: { length: 8, length2: 8 } }],
  };
}

export function heatmapOption(s: Season, fmt: Fmt) {
  const max = Math.max(...s.cells.map((c) => c.value), 1);
  return {
    animation: false, textStyle: { fontFamily: "inherit" }, grid: { left: 6, right: 12, top: 8, bottom: 52, containLabel: true },
    tooltip: { confine: true, formatter: (p: { value: [number, number, number] }) => `${s.years[p.value[1]]} · ${fmt.month(p.value[0] + 1)}<br/><b>${fmt.ntd(p.value[2])}</b>` },
    xAxis: { type: "category" as const, data: Array.from({ length: 12 }, (_, i) => fmt.month(i + 1)), splitArea: { show: true }, axisLabel: axisText },
    yAxis: { type: "category" as const, data: s.years.map(String), axisLabel: axisText, inverse: true },
    visualMap: { min: 0, max, calculable: false, orient: "horizontal" as const, left: "center", bottom: 4, itemWidth: 14, itemHeight: 160, textStyle: { color: C.muted },
      inRange: { color: ["#ecfdf5", "#99f6e4", "#0d9488", "#115e59"] }, formatter: (v: number) => fmt.axisMoney(Math.round(v)) },
    series: [{ type: "heatmap" as const, data: s.cells.map((c) => [c.month - 1, s.years.indexOf(c.year), c.value]), itemStyle: { borderColor: "#fff", borderWidth: 3, borderRadius: 6 }
    }],
  };
}

/** Share of the money held by the top x% of donors, with the "everyone gives equally" diagonal for reference. */
export function concentrationOption(c: Concentration, t: T) {
  const b = baseOption();
  const line = (name: string, key: "all" | "ordinary", color: string, dashed = false) => ({
    name, type: "line" as const, data: c.curve.map((p) => [p.pct, +(p[key] * 100).toFixed(1)]), symbol: "none", smooth: false,
    lineStyle: { width: 3, color, type: dashed ? ("dashed" as const) : ("solid" as const) }, itemStyle: { color },
  });
  return {
    ...b, tooltip: { ...b.tooltip, trigger: "axis" as const, axisPointer: { type: "line" as const }, valueFormatter: (v: number) => `${v}%` },
    xAxis: { type: "value" as const, min: 0, max: 100, name: t("conc.x"), nameLocation: "middle" as const, nameGap: 28, axisLabel: { ...axisText, formatter: "{value}%" }, splitLine: { show: false } },
    yAxis: { type: "value" as const, min: 0, max: 100, axisLabel: { ...axisText, formatter: "{value}%" }, splitLine: { lineStyle: { color: C.line, type: "dashed" as const } } },
    series: [line(t("conc.all"), "all", C.exceptional), line(t("conc.ordinary"), "ordinary", C.regular),
      { name: t("conc.equal"), type: "line" as const, data: [[0, 0], [100, 100]], symbol: "none", lineStyle: { width: 2, color: C.grey, type: "dashed" as const }, tooltip: { show: false } }],
  };
}

/** Where donors go year to year: stayed, stopped, newly arrived, came back. */
export function sankeyOption(j: Journey, t: T) {
  const ys = j.years.filter((y) => y.history_available);
  const first = j.years[0];
  const nodes: { name: string; itemStyle: { color: string } }[] = [{ name: t("sankey.donors", { year: first.year }), itemStyle: { color: C.slate } }];
  const links: { source: string; target: string; value: number }[] = [];
  const have = new Set(nodes.map((n) => n.name));
  const add = (name: string, color: string) => { if (!have.has(name)) { have.add(name); nodes.push({ name, itemStyle: { color } }); } return name; };
  let prev = nodes[0].name;
  for (const y of ys) {
    const cur = add(t("sankey.donors", { year: y.year }), C.slate);
    if (y.retained) links.push({ source: prev, target: cur, value: y.retained });
    if (y.lapsed) links.push({ source: prev, target: add(t("sankey.stopped", { year: y.year }), C.rose), value: y.lapsed });
    if (y.new) links.push({ source: add(t("sankey.new", { year: y.year }), C.regular), target: cur, value: y.new });
    if (y.reactivated) links.push({ source: add(t("sankey.back", { year: y.year }), C.sky), target: cur, value: y.reactivated });
    prev = cur;
  }
  return {
    animation: false, textStyle: { fontFamily: "inherit" },
    tooltip: { trigger: "item" as const, confine: true, formatter: (p: { name: string; value: number; dataType: string }) => (p.dataType === "edge" ? `${p.name}: <b>${p.value}</b>` : `${p.name}: <b>${p.value}</b>`) },
    series: [{ type: "sankey" as const, data: nodes, links, left: 6, right: 90, top: 8, bottom: 8, nodeWidth: 16, nodeGap: 14, draggable: false, emphasis: { focus: "adjacency" as const },
      lineStyle: { color: "gradient" as const, curveness: 0.5, opacity: 0.35 }, label: { color: C.ink, fontSize: 12 } }],
  };
}

/** Each bubble is a donor: how much they gave, how likely they are to stop, and (size) the money at stake. */
export function bubbleOption(points: RiskPoint[], fmt: Fmt, t: T) {
  const b = baseOption();
  const maxVar = Math.max(...points.map((p) => p.value_at_risk), 1);
  const byClass = new Map<string, RiskPoint[]>();
  for (const p of points) byClass.set(p.donor_class_label, [...(byClass.get(p.donor_class_label) ?? []), p]);
  return {
    ...b, grid: { ...b.grid, top: 38, bottom: 30 },
    tooltip: { trigger: "item" as const, confine: true, formatter: (p: { data: { p: RiskPoint } }) => {
      const d = p.data.p;
      return `<b>${d.donor_id}</b> · ${d.donor_class_label}<br/>${t("bubble.gave")}: ${fmt.ntd(d.giving_last_year)}<br/>${t("bubble.chance")}: ${fmt.pct(d.p_lapse, 0)}<br/>${t("bubble.var")}: <b>${fmt.compact(d.value_at_risk)}</b>`;
    } },
    xAxis: { type: "log" as const, min: 500, name: t("bubble.x"), nameLocation: "middle" as const, nameGap: 28, axisLabel: { ...axisText, formatter: (v: number) => fmt.axisMoney(v) }, splitLine: { lineStyle: { color: C.line, type: "dashed" as const } } },
    yAxis: { type: "value" as const, min: 0, max: 100, name: t("bubble.y"), nameTextStyle: { align: "left" as const, color: C.muted, fontSize: 12 }, axisLabel: { ...axisText, formatter: "{value}%" }, splitLine: { lineStyle: { color: C.line, type: "dashed" as const } } },
    series: [...byClass].map(([name, pts], i) => ({
      name, type: "scatter" as const, itemStyle: { color: PALETTE[i % PALETTE.length], opacity: 0.72, borderColor: "#fff", borderWidth: 1 },
      data: pts.map((p) => ({ value: [Math.max(p.giving_last_year, 500), +(p.p_lapse * 100).toFixed(1)], p })),
      symbolSize: (_v: unknown, params: { data: { p: RiskPoint } }) => 8 + 40 * Math.sqrt(params.data.p.value_at_risk / maxVar),
    })),
  };
}

/** Ordinary giving so far, and where it could go next year (a range, never a single promised number). */
export function fanOption(s: Scenario, fmt: Fmt, t: T, goal = 0) {
  const hist = s.history.map((h) => h.ordinary);
  const years = [...s.history.map((h) => String(h.year)), String(s.projection_year)];
  const pad = (v: number | null[]) => v;
  const n = hist.length, last = hist[n - 1];
  const gap = Array(n - 1).fill(null);
  const band = (name: string, stack: string, color: string, lo: number, hi: number) => [
    { name: `${name}-lo`, type: "line" as const, stack, data: [...gap, last, lo], symbol: "none", lineStyle: { opacity: 0 }, areaStyle: { color: "transparent" }, silent: true, tooltip: { show: false } },
    { name: `${name}-band`, type: "line" as const, stack, data: [...gap, 0, hi - lo], symbol: "none", lineStyle: { opacity: 0 }, areaStyle: { color, opacity: 0.22 }, silent: true, tooltip: { show: false } },
  ];
  const b = baseOption();
  void pad;
  return {
    ...b, grid: { ...b.grid, right: 40 }, legend: { ...b.legend, data: [t("fan.history"), t("fan.baseline"), t("fan.scenario")] }, tooltip: { ...b.tooltip, trigger: "axis" as const, axisPointer: { type: "line" as const }, hideDelay: 1200, ...tip(fmt) },
    xAxis: { type: "category" as const, data: years, boundaryGap: false, axisLabel: axisText },
    // start the axis near the data: from zero the plausible range would be a flat line
    yAxis: { ...yMoney(fmt.axisMoney), min: Math.floor(Math.min(...hist, s.baseline.low, s.scenario.low) * 0.85 / 1e6) * 1e6 },
    series: [
      ...band("b", "sb", C.slate, s.baseline.low, s.baseline.high), ...band("s", "ss", C.regular, s.scenario.low, s.scenario.high),
      { name: t("fan.history"), type: "line" as const, data: [...hist, null], symbol: "circle", symbolSize: 9, lineStyle: { width: 3, color: C.indigo }, itemStyle: { color: C.indigo },
        label: { show: true, position: "top" as const, color: C.muted, fontSize: 11, formatter: (p: { value: number | null }) => (p.value == null ? "" : fmt.compact(p.value)) } },
      { name: t("fan.baseline"), type: "line" as const, data: [...gap, last, s.baseline.expected], symbol: "circle", symbolSize: 9, lineStyle: { width: 3, color: C.slate, type: "dashed" as const }, itemStyle: { color: C.slate } },
      { name: t("fan.scenario"), type: "line" as const, data: [...gap, last, s.scenario.expected], symbol: "circle", symbolSize: 11, lineStyle: { width: 3.5, color: C.regular }, itemStyle: { color: C.regular },
        label: { show: true, position: (goal > 0 ? "bottom" : "top") as "top" | "bottom", color: C.ink, fontWeight: 700, fontSize: 12, formatter: (p: { dataIndex: number; value: number | null }) => (p.dataIndex === years.length - 1 && p.value != null ? fmt.compact(p.value) : "") } },
      ...(goal > 0 ? [{ name: t("gp.goal_name"), type: "scatter" as const, data: [...gap, null, s.baseline.expected + goal].map((v) => v ?? "-"), symbol: "diamond", symbolSize: 13, itemStyle: { color: C.rose },
        label: { show: true, position: "top" as const, color: C.rose, fontWeight: 700, fontSize: 12, formatter: (p: { value: number | string }) => (typeof p.value === "number" ? t("gp.goal_line", { amount: fmt.compact(p.value) }) : "") } }] : []),
    ],
  };
}

export function monthlyOption(months: { month: number; regular: number; exceptional: number; total: number }[], log: boolean, fmt: Fmt, t: T) {
  const b = baseOption();
  const series = log
    ? [{ name: t("series.all"), type: "bar" as const, data: months.map((m) => (m.total > 0 ? m.total : null)), itemStyle: { color: C.slate, borderRadius: [6, 6, 0, 0] } }]
    : [
        { name: t("series.ordinary"), type: "bar" as const, stack: "m", data: months.map((m) => m.regular), itemStyle: { color: C.regular } },
        { name: t("series.exceptional"), type: "bar" as const, stack: "m", data: months.map((m) => m.exceptional), itemStyle: { color: C.exceptional, borderRadius: [6, 6, 0, 0] } },
      ];
  return { ...b, tooltip: { ...b.tooltip, ...tip(fmt) }, xAxis: { type: "category" as const, data: months.map((m) => fmt.month(m.month)), axisLabel: axisText }, yAxis: yMoney(fmt.axisMoney, log), series };
}

export function hbar(rows: Breakdown[], fmt: Fmt) {
  const r = [...rows].reverse();
  const b = baseOption();
  return {
    ...b, legend: undefined, tooltip: { ...b.tooltip, ...tip(fmt) }, grid: { left: 6, right: 70, top: 8, bottom: 6, containLabel: true },
    xAxis: { type: "value" as const, axisLabel: { ...axisText, formatter: (v: number) => fmt.axisMoney(v) }, splitLine: { lineStyle: { color: C.line, type: "dashed" as const } } },
    yAxis: { type: "category" as const, data: r.map((x) => x.label), axisLabel: axisText },
    series: [{ type: "bar" as const, data: r.map((x) => x.amount ?? 0), itemStyle: { color: C.regular, borderRadius: [0, 6, 6, 0] }, barMaxWidth: 22,
      label: { show: true, position: "right" as const, color: C.muted, fontSize: 12, formatter: (p: { value: number }) => fmt.compact(p.value) } }],
  };
}
