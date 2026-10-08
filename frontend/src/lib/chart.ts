import { BarChart, HeatmapChart, LineChart, PieChart, SankeyChart, ScatterChart, TreemapChart } from "echarts/charts";
import { GridComponent, LegendComponent, MarkLineComponent, TooltipComponent, VisualMapComponent } from "echarts/components";
import * as echarts from "echarts/core";
import { LegacyGridContainLabel } from "echarts/features";
import { CanvasRenderer } from "echarts/renderers";

echarts.use([BarChart, LineChart, PieChart, ScatterChart, HeatmapChart, TreemapChart, SankeyChart,
  GridComponent, TooltipComponent, LegendComponent, MarkLineComponent, VisualMapComponent, LegacyGridContainLabel, CanvasRenderer]);
export { echarts };

/** Colour means the same thing everywhere: teal = ordinary giving, amber = exceptional, green/rose = up/down, violet = AI. */
export const C = {
  regular: "#0d9488", exceptional: "#f59e0b", indigo: "#4f46e5", sky: "#0ea5e9", rose: "#e11d48", olive: "#65a30d",
  violet: "#7c3aed", green: "#16a34a", slate: "#64748b", grey: "#cbd5e1", ink: "#0f172a", muted: "#64748b", line: "#e2e8f0",
};
export const PALETTE = [C.regular, C.indigo, C.exceptional, C.sky, C.rose, C.violet, C.olive, C.slate];

export const axisText = { color: C.muted, fontSize: 12 };
// Animation is off on purpose: charts are screenshotted and exported, and the grow-in stalls in background tabs.
export const baseOption = () => ({
  animation: false,
  color: PALETTE,
  textStyle: { fontFamily: "inherit" },
  grid: { left: 6, right: 18, top: 34, bottom: 6, containLabel: true },
  tooltip: { trigger: "axis" as const, axisPointer: { type: "shadow" as const }, confine: true, borderColor: C.line, textStyle: { color: C.ink } },
  legend: { top: 0, right: 0, icon: "roundRect", itemWidth: 12, itemHeight: 12, textStyle: { color: C.muted, fontSize: 12 } },
});
export const yMoney = (axisMoney: (v: number) => string, log = false) => ({
  type: (log ? "log" : "value") as "log" | "value",
  axisLabel: { ...axisText, formatter: (v: number) => axisMoney(v) },
  splitLine: { lineStyle: { color: C.line, type: "dashed" as const } },
  ...(log ? { min: 1000 } : {}),
});
