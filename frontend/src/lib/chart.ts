import { BarChart, HeatmapChart, LineChart, PieChart, SankeyChart, ScatterChart, TreemapChart } from "echarts/charts";
import { GridComponent, LegendComponent, MarkLineComponent, TooltipComponent, VisualMapComponent } from "echarts/components";
import * as echarts from "echarts/core";
import { LegacyGridContainLabel } from "echarts/features";
import { CanvasRenderer } from "echarts/renderers";

echarts.use([BarChart, LineChart, PieChart, ScatterChart, HeatmapChart, TreemapChart, SankeyChart,
  GridComponent, TooltipComponent, LegendComponent, MarkLineComponent, VisualMapComponent, LegacyGridContainLabel, CanvasRenderer]);
export { echarts };

/** Colour means the same thing everywhere: pine = ordinary giving, wheat = exceptional, green/rose = up/down, plum = AI. */
export const C = {
  regular: "#4f7a68", exceptional: "#c4a574", indigo: "#6b5e52", sky: "#8aa396", rose: "#8f4d52", olive: "#6e8b74",
  violet: "#5e5670", green: "#3e6b4a", slate: "#8a8178", grey: "#d9d3cb", ink: "#2c2825", muted: "#70675e", line: "#e7e1d8",
};
/** Pine only, light to deep. Wheat stays reserved for exceptional giving. */
const YEAR_SCALE = ["#6d8d7d", "#4f7a68", "#416b59", "#2f5648", "#243f35"];

/** Years run light to deep. Three years use the ends and the middle so neighbours stay apart. */
export function yearColors(count: number): string[] {
  if (count <= 0) return [];
  if (count === 1) return [YEAR_SCALE[2]];
  if (count <= YEAR_SCALE.length) {
    return Array.from({ length: count }, (_, i) => YEAR_SCALE[Math.round((i * (YEAR_SCALE.length - 1)) / (count - 1))]);
  }
  return Array.from({ length: count }, (_, i) => YEAR_SCALE[Math.min(i, YEAR_SCALE.length - 1)]);
}
export const PALETTE = ["#2f5648", "#4f7a68", "#8aa396", "#6b5e52", "#a89880", "#5c6b62", "#8a8178", "#3d4a44"];

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
