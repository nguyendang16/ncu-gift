import { useEffect, useRef, useState } from "react";
import type { EChartsCoreOption } from "echarts/core";
import * as EChartsModule from "echarts-for-react/lib/core";
import { useI18n } from "../i18n";
import { echarts } from "../lib/chart";
import { downloadDataUrl, fileStem, registerChart } from "../lib/download";

// echarts-for-react ships CommonJS; depending on the bundler the component arrives as the module itself or as
// `.default`. Resolve both so the same code works in `vite dev` and in the production build.
type Comp = typeof EChartsModule.default;
const ReactEChartsCore: Comp =
  (EChartsModule as unknown as { default: { default?: Comp } & Comp }).default.default ??
  (EChartsModule as unknown as { default: Comp }).default;

type ChartHandle = {
  getEchartsInstance: () => {
    resize: () => void;
    getDataURL: (opts: { type: "png"; pixelRatio: number; backgroundColor: string }) => string;
  };
};

/** `label` is the accessible description of the chart; tables next to each chart carry the same data.
 *  `exportName` is the file name for the PNG. It defaults to `label`. */
export function Chart({ option, height = 280, label, exportName }: { option: EChartsCoreOption; height?: number; label: string; exportName?: string }) {
  const { t } = useI18n();
  const ref = useRef<ChartHandle>(null);
  const [ready, setReady] = useState(false);
  const name = exportName ?? label;

  const png = () => {
    const chart = ref.current?.getEchartsInstance();
    if (!chart) return null;
    chart.resize();
    return chart.getDataURL({ type: "png", pixelRatio: 2, backgroundColor: "#ffffff" });
  };

  useEffect(() => {
    if (!ready) return;
    return registerChart({ name, png });
  }, [ready, name]);

  return (
    <div>
      <div className="chart-tools">
        <button type="button" className="btn tiny" aria-label={t("export.png_label")} disabled={!ready} onClick={() => {
          const url = png();
          if (url) downloadDataUrl(`${fileStem(name)}.png`, url);
        }}>{t("export.png")}</button>
      </div>
      <div role="img" aria-label={label}>
        <ReactEChartsCore ref={ref as never} echarts={echarts} option={option} style={{ height }} notMerge opts={{ renderer: "canvas" }} onChartReady={() => setReady(true)} />
      </div>
    </div>
  );
}
