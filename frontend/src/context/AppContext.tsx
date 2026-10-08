import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { useDatasets } from "../api/hooks";
import type { Dataset } from "../api/types";

export type Settings = { exceptional: number; large: number; returnDef: string };
const DEFAULTS: Settings = { exceptional: 10_000_000, large: 100_000, returnDef: "retained" };

type Ctx = {
  datasets: Dataset[]; dataset?: Dataset; datasetId?: number; setDatasetId: (id: number) => void;
  settings: Settings; setSettings: (s: Settings) => void;
};
const AppCtx = createContext<Ctx>(null as unknown as Ctx);
export const useApp = () => useContext(AppCtx);

const read = <T,>(key: string, fallback: T): T => {
  try { const v = localStorage.getItem(key); return v ? (JSON.parse(v) as T) : fallback; } catch { return fallback; }
};
const write = (key: string, v: unknown) => { try { localStorage.setItem(key, JSON.stringify(v)); } catch { /* storage unavailable */ } };

export function AppProvider({ children }: { children: ReactNode }) {
  const { data: datasets = [] } = useDatasets();
  const [picked, setPicked] = useState<number | undefined>(() => read<number | undefined>("ncu.dataset", undefined));
  const [settings, setSettingsState] = useState<Settings>(() => ({ ...DEFAULTS, ...read<Partial<Settings>>("ncu.settings", {}) }));
  const dataset = datasets.find((d) => d.id === picked) ?? datasets[0];
  useEffect(() => { if (dataset) write("ncu.dataset", dataset.id); }, [dataset]);
  const value = useMemo<Ctx>(() => ({
    datasets, dataset, datasetId: dataset?.id, setDatasetId: setPicked,
    settings, setSettings: (s) => { setSettingsState(s); write("ncu.settings", s); },
  }), [datasets, dataset, settings]);
  return <AppCtx.Provider value={value}>{children}</AppCtx.Provider>;
}
