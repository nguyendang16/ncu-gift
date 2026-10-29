/** The two charts of the Goal planner. Both are zoomed on next year, so dragging a slider visibly moves them
 *  (a one-million change disappears on a chart that also has to show the whole history). */
import type { Scenario } from "../api/types";
import type { Fmt } from "../i18n";
import { C, axisText, baseOption } from "./chart";
import type { T } from "./options";

/** "If nothing changes" against "Your plan": each as a range (likely low to high) with the expected value marked. */
export function rangeOption(sc: Scenario, fmt: Fmt, t: T, goal = 0) {
  const rows = [
    { n: t("gp.your_plan"), expected: sc.scenario.expected, low: sc.scenario.low, high: sc.scenario.high, color: C.regular },
    { n: t("gp.if_nothing"), expected: sc.baseline.expected, low: sc.baseline.low, high: sc.baseline.high, color: C.slate },
  ];
  const target = goal > 0 ? sc.baseline.expected + goal : null;
  const lo = Math.min(...rows.map((r) => r.low)), hi = Math.max(...rows.map((r) => r.high), target ?? 0);
  const pad = (hi - lo) * 0.18 || hi * 0.02;
  const min = lo - pad, max = hi + pad;
  const b = baseOption();
  return {
    animation: false, textStyle: b.textStyle,
    grid: { left: 6, right: 56, top: target ? 46 : 22, bottom: 26, containLabel: true },
    tooltip: { trigger: "item" as const, confine: true, hideDelay: 1200, formatter: (p: { dataIndex: number }) => {
      const r = rows[p.dataIndex]; return `<b>${r.n}</b><br/>${t("strategy.tt_expected", { amount: fmt.ntd(r.expected) })}<br/>${t("strategy.tt_range", { low: fmt.ntd(r.low), high: fmt.ntd(r.high) })}`; } },
    xAxis: { type: "value" as const, min, max, axisLabel: { ...axisText, formatter: (v: number) => fmt.compact(v).replace("NT$", "") }, splitLine: { lineStyle: { color: C.line, type: "dashed" as const } } },
    yAxis: { type: "category" as const, data: rows.map((r) => r.n), inverse: true, axisLabel: { color: C.ink, fontSize: 12, fontWeight: 600 }, axisLine: { show: false }, axisTick: { show: false } },
    series: [
      { type: "bar" as const, stack: "r", data: rows.map((r) => r.low), itemStyle: { color: "transparent" }, silent: true, tooltip: { show: false } },
      { type: "bar" as const, stack: "r", barWidth: 26, data: rows.map((r) => ({ value: r.high - r.low, itemStyle: { color: r.color, opacity: 0.35, borderRadius: 8 } })) },
      { type: "scatter" as const, symbol: "circle", symbolSize: 1, itemStyle: { color: "transparent" }, silent: true, data: rows.map((r, i) => ({ value: [r.low, i] })),
        label: { show: true, position: "left" as const, color: C.muted, fontSize: 11, formatter: (p: { dataIndex: number }) => fmt.compact(rows[p.dataIndex].low) } },
      { type: "scatter" as const, symbol: "circle", symbolSize: 1, itemStyle: { color: "transparent" }, silent: true, data: rows.map((r, i) => ({ value: [r.high, i] })),
        label: { show: true, position: "right" as const, color: C.muted, fontSize: 11, formatter: (p: { dataIndex: number }) => fmt.compact(rows[p.dataIndex].high) } },
      { type: "scatter" as const, symbol: "rect", symbolSize: [4, 34], data: rows.map((r, i) => ({ value: [r.expected, i], itemStyle: { color: r.color } })),
        label: { show: true, position: "top" as const, color: C.ink, fontWeight: 700, fontSize: 12, formatter: (p: { dataIndex: number }) => fmt.compact(rows[p.dataIndex].expected) },
        markLine: target === null ? undefined : { silent: true, symbol: "none", animation: false, lineStyle: { color: C.rose, type: "dashed" as const, width: 2 },
          label: { show: true, position: "start" as const, distance: 22, color: C.rose, fontWeight: 700, fontSize: 12, formatter: () => t("gp.goal_line", { amount: fmt.compact(target) }) }, data: [{ xAxis: target }] } },
    ],
  };
}

/** Where the extra comes from: what each group adds compared with doing nothing. Empty until a lever moves. */
export function addsParts(sc: Scenario) {
  return sc.cohorts.map((c) => ({ name: c.cohort, value: c.expected_scenario - c.expected_base })).filter((p) => Math.abs(p.value) >= 1000);
}

export function addsOption(parts: { name: string; value: number }[], fmt: Fmt) {
  const b = baseOption();
  return {
    animation: false, textStyle: b.textStyle,
    grid: { left: 6, right: 70, top: 6, bottom: 6, containLabel: true },
    tooltip: { trigger: "item" as const, confine: true, valueFormatter: (v: number) => fmt.ntd(v) },
    xAxis: { type: "value" as const, show: false },
    yAxis: { type: "category" as const, data: parts.map((p) => p.name), inverse: true, axisLabel: { color: C.ink, fontSize: 12, width: 150, overflow: "break" as const }, axisLine: { show: false }, axisTick: { show: false } },
    series: [{ type: "bar" as const, barMaxWidth: 24, data: parts.map((p) => ({ value: p.value, itemStyle: { color: p.value >= 0 ? C.regular : C.rose, borderRadius: p.value >= 0 ? [0, 8, 8, 0] : [8, 0, 0, 8] } })),
      label: { show: true, position: "right" as const, color: C.ink, fontWeight: 650, fontSize: 12, formatter: (p: { value: number }) => `${p.value >= 0 ? "+" : "−"}${fmt.compact(Math.abs(p.value))}` } }],
  };
}
