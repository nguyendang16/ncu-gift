import type { EChartsCoreOption } from "echarts/core";
import * as EChartsModule from "echarts-for-react/lib/core";
import { echarts } from "../lib/chart";

// echarts-for-react ships CommonJS; depending on the bundler the component arrives as the module itself or as
// `.default`. Resolve both so the same code works in `vite dev` and in the production build.
type Comp = typeof EChartsModule.default;
const ReactEChartsCore: Comp =
  (EChartsModule as unknown as { default: { default?: Comp } & Comp }).default.default ??
  (EChartsModule as unknown as { default: Comp }).default;

/** `label` is the accessible description of the chart; tables next to each chart carry the same data. */
export function Chart({ option, height = 280, label }: { option: EChartsCoreOption; height?: number; label: string }) {
  return (
    <div role="img" aria-label={label}>
      <ReactEChartsCore echarts={echarts} option={option} style={{ height }} notMerge opts={{ renderer: "canvas" }} />
    </div>
  );
}
