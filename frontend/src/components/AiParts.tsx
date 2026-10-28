import { Link } from "react-router-dom";
import { useAiDock } from "./ai/dockContext";
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
  if (v.ok && v.checked === 0) return null;          // nothing to check: no badge rather than "0 numbers checked"
  return v.ok
    ? <span className="pill ok"><Icon name="check" size={13} /> {t("ai.verified", { n: v.checked })}</span>
    : <span className="pill caveat" title={v.unverified.join(", ")}><Icon name="risk" size={13} /> {t("ai.unverified", { list: v.unverified.join(", ") })}</span>;
}

/** The plain-language summary on the Overview. Costs a fraction of a cent; runs only when asked. */
export function AiSummary({ year }: { year?: number }) {
  const { datasetId, settings } = useApp();
  const { t } = useI18n();
  const { ready } = useAiReady();
  const { ask } = useAiDock();
  const run = useInsights();
  const r = run.data;
  const labels: Record<string, string> = {
    compare: t("ai.obs.compare"),
    base: t("ai.obs.base"),
    concentration: t("ai.obs.concentration"),
    accounts: t("ai.obs.accounts"),
  };
  return (
    <Card ai icon="ai" title={t("ai.summary_title")} sub={t("ai.summary_sub")}
      right={<button className="btn ai" disabled={!ready || run.isPending} onClick={() => run.mutate({ dataset_id: datasetId, year, exceptional_threshold: settings.exceptional, large_threshold: settings.large })}>
        <Icon name="ai" size={17} />{run.isPending ? t("ai.thinking") : r ? t("ai.summary_again") : t("ai.summary_button")}</button>}>
      {!ready && <AiOffHint />}
      <DemoNotice />
      {run.isError && <ErrorView error={run.error} />}
      {r && (
        <div className="rise">
          <h3 className="brief-title">{t("ai.brief_title")}</h3>
          <section className="brief-col">
            <h3>{t("ai.observe")}</h3>
            <div className="obs-grid">
              {r.observations.map((item) => (
                <div className="obs-row" key={item.key}>
                  <span className="obs-tag">{labels[item.key] ?? item.key}</span>
                  <p>{item.text}</p>
                </div>
              ))}
            </div>
          </section>
          <section className="brief-col" style={{ marginTop: 16 }}>
            <h3>{t("ai.actions_title")}</h3>
            {(r.actions ?? []).length > 0 ? (
              <div className="act-grid">
                {(r.actions ?? []).map((a, i) => (
                  <article className="act" key={a.candidate_id}>
                    <header><span className="act-n">{i + 1}</span><h4>{a.title}</h4></header>
                    <p>{a.why}</p>
                    {a.now && <p className="act-now">{a.now}</p>}
                    <div className="act-label">{t("ai.act.steps")}</div>
                    <ol>{a.steps.map((st, j) => <li key={j}>{st}</li>)}</ol>
                    <div className="act-effect"><b>{t("ai.act.effect")}</b> {a.expected_effect}</div>
                    {a.measure && <div className="small muted act-measure">{a.measure}</div>}
                    <div className="act-btns">
                      <Link className="btn" to={a.link.to}>{a.link.label} →</Link>
                      <button className="btn go" onClick={() => ask(t("ai.ask_how", { title: a.title }))}><Icon name="ai" size={15} />{t("ai.ask_help")}</button>
                    </div>
                  </article>
                ))}
              </div>
            ) : (
              <ol className="advice">
                {r.recommendations.map((text, i) => (
                  <li key={i}><span>{String(i + 1).padStart(2, "0")}</span><p>{text}</p></li>
                ))}
              </ol>
            )}
          </section>
          <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap", marginTop: 12 }}>
            <VerifyBadge v={r.verification} />
            {r.demo && <span className="small muted">{t("ai.by_demo")}</span>}
          </div>
        </div>
      )}
      {ready && !r && !run.isPending && !run.isError && <p className="muted small" style={{ margin: 0 }}>{t("ai.summary_idle")}</p>}
    </Card>
  );
}
