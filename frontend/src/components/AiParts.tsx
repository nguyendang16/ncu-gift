import { Link } from "react-router-dom";
import { useAiStatus, useInsights } from "../api/hooks";
import type { NumberCheck } from "../api/types";
import { useApp } from "../context/AppContext";
import { useI18n } from "../i18n";
import { Card, ErrorView, Icon, Notice } from "./ui";

export function useAiReady() {
  const q = useAiStatus();
  return { status: q.data, ready: !!q.data?.ready, loading: q.isPending };
}

/** Shown wherever an AI button lives while AI is off or not configured: says what to do, in one sentence. */
export function AiOffHint() {
  const { t } = useI18n();
  const { status } = useAiReady();
  if (!status || status.ready) return null;
  return (
    <Notice tone="ai" title={t("ai.hint_setup_title")}>
      {t("ai.hint_setup")} <Link to="/ai">{t("ai.open_settings")}</Link>
    </Notice>
  );
}

export function DemoNotice() {
  const { t } = useI18n();
  const { status } = useAiReady();
  if (!status?.demo) return null;
  return <Notice tone="warn" title={t("ai.demo_title")}>{t("ai.demo_text")}</Notice>;
}

/** Every figure the AI quoted was checked against the summary it was given. This says so, or says which ones were not found. */
export function VerifyBadge({ v }: { v: NumberCheck }) {
  const { t } = useI18n();
  return v.ok
    ? <span className="pill ok"><Icon name="check" size={13} /> {t("ai.verified", { n: v.checked })}</span>
    : <span className="pill caveat" title={v.unverified.join(", ")}><Icon name="risk" size={13} /> {t("ai.unverified", { list: v.unverified.join(", ") })}</span>;
}

/** The plain-language summary on the Overview. Costs a fraction of a cent; runs only when asked. */
export function AiSummary({ year }: { year?: number }) {
  const { datasetId, settings } = useApp();
  const { t } = useI18n();
  const { ready } = useAiReady();
  const run = useInsights();
  const r = run.data;
  return (
    <Card ai icon="ai" title={t("ai.summary_title")} sub={t("ai.summary_sub")}
      right={<button className="btn ai" disabled={!ready || run.isPending} onClick={() => run.mutate({ dataset_id: datasetId, year, exceptional_threshold: settings.exceptional, large_threshold: settings.large })}>
        <Icon name="ai" size={17} />{run.isPending ? t("ai.thinking") : r ? t("ai.summary_again") : t("ai.summary_button")}</button>}>
      {!ready && <AiOffHint />}
      <DemoNotice />
      {run.isError && <ErrorView error={run.error} />}
      {r && (
        <div className="rise">
          <p style={{ fontSize: "1.1rem", fontWeight: 650, margin: "0 0 10px" }}>{r.headline}</p>
          <ul style={{ margin: "0 0 12px", paddingLeft: 20, display: "grid", gap: 6 }}>{r.points.map((p, i) => <li key={i}>{p}</li>)}</ul>
          <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
            <VerifyBadge v={r.verification} />
            {r.demo && <span className="small muted">{t("ai.by_demo")}</span>}
          </div>
        </div>
      )}
      {ready && !r && !run.isPending && !run.isError && <p className="muted small" style={{ margin: 0 }}>{t("ai.summary_idle")}</p>}
    </Card>
  );
}
