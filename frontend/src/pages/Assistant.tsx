import { Fragment, useEffect, useRef, useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { useAgent } from "../api/hooks";
import type { AgentOut, AgentStep, AiTurn } from "../api/types";
import { DemoNotice, VerifyBadge, useAiReady } from "../components/AiParts";
import { Accordion, Card, EmptyState, ErrorView, Icon, PageHeader } from "../components/ui";
import { useApp } from "../context/AppContext";
import { useI18n } from "../i18n";
import type { Key } from "../i18n/en";

const SUGGESTED: Key[] = ["ai.q1", "ai.q2", "ai.q3", "ai.q4"];

type Turn = { q: string; a: AgentOut };

/** Models sometimes still wrap figures in **bold**. And [n] marks the analysis a figure came from: shown as a small numbered chip. */
function plain(text: string): ReactNode {
  return text.split(/(\*\*[^*]+\*\*|\[\d{1,2}\])/g).map((part, i) => {
    if (part.startsWith("**") && part.endsWith("**") && part.length > 4) return <b key={i}>{part.slice(2, -2)}</b>;
    const m = /^\[(\d{1,2})\]$/.exec(part);
    if (m) return <a key={i} className="cite" href={`#src-${m[1]}`} onClick={(e) => { e.preventDefault(); document.getElementById(`src-${m[1]}`)?.scrollIntoView({ behavior: "smooth", block: "center" }); }}>{m[1]}</a>;
    return <Fragment key={i}>{part}</Fragment>;
  });
}

function StepCard({ s }: { s: AgentStep }) {
  const { t } = useI18n();
  return (
    <div className={`step ${s.ok ? "" : "bad"}`} id={`src-${s.n}`}>
      <div className="step-h"><span className="cite static">{s.n}</span><b>{s.title}</b>{s.args_text && <span className="muted small"> · {s.args_text}</span>}</div>
      <div className="small">{s.summary}</div>
      {s.table && (
        <div className="scroll"><table className="t">
          <thead><tr>{s.table.columns.map((c) => <th key={c}>{c}</th>)}</tr></thead>
          <tbody>{s.table.rows.map((r, i) => <tr key={i}>{r.map((v, j) => <td key={j} className={j === 0 ? "mono" : ""}>{String(v)}</td>)}</tr>)}</tbody>
        </table></div>
      )}
      {s.link && <Link className="btn" style={{ marginTop: 8 }} to={s.link}>{t("ai.open_strategy")} →</Link>}
    </div>
  );
}

function Chat() {
  const { datasetId, settings } = useApp();
  const { t } = useI18n();
  const { ready, status } = useAiReady();
  const ask = useAgent();
  const [turns, setTurns] = useState<Turn[]>([]);
  const [text, setText] = useState("");
  const end = useRef<HTMLDivElement>(null);
  useEffect(() => { end.current?.scrollIntoView({ behavior: "smooth", block: "nearest" }); }, [turns.length, ask.isPending]);
  const send = (q: string) => {
    q = q.trim();
    if (!q || !ready || ask.isPending) return;
    const history: AiTurn[] = turns.slice(-3).map((x) => ({ question: x.q, answer: x.a.answer }));
    ask.mutate({ dataset_id: datasetId, question: q, history, exceptional_threshold: settings.exceptional, large_threshold: settings.large }, { onSuccess: (a) => { setTurns((p) => [...p, { q, a }]); setText(""); } });
  };
  return (
    <Card ai icon="chat" title={t("ai.chat_title")} sub={t("ai.chat_sub")}>
      <DemoNotice />
      <div className="chat" aria-live="polite">
        {turns.length === 0 && !ask.isPending && (
          <EmptyState icon="chat" title={t("ai.chat_empty")}>
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap", justifyContent: "center", marginTop: 10 }}>
              {SUGGESTED.map((k) => <button key={k} className="btn" disabled={!ready} onClick={() => send(t(k))}>{t(k)}</button>)}
            </div>
          </EmptyState>
        )}
        {turns.map((x, i) => (
          <div key={i} style={{ display: "grid", gap: 10 }}>
            <div className="msg user">{x.q}</div>
            <div className="msg bot">
              {plain(x.a.answer)}
              <div className="meta">
                <VerifyBadge v={x.a.verification} />
                {x.a.demo && <span>{t("ai.by_demo")}</span>}
              </div>
              {x.a.steps.length > 0 && (
                <div className="steps" style={{ whiteSpace: "normal" }}>
                  <div className="steps-h">{t("ai.how")}</div>
                  {x.a.steps.map((s) => <StepCard key={s.n} s={s} />)}
                </div>
              )}
            </div>
          </div>
        ))}
        {ask.isPending && <div className="msg bot muted">{t("ai.working")}</div>}
        {ask.isError && <ErrorView error={ask.error} />}
        <div ref={end} />
      </div>
      <form className="chat-input" style={{ marginTop: 14 }} onSubmit={(e) => { e.preventDefault(); send(text); }}>
        <textarea value={text} placeholder={t("ai.chat_placeholder")} aria-label={t("ai.chat_placeholder")} disabled={!ready}
          onChange={(e) => setText(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(text); } }} />
        <button className="btn ai" type="submit" disabled={!ready || ask.isPending || !text.trim()}><Icon name="send" size={17} />{t("ai.send")}</button>
      </form>
      {!ready && status && <p className="small muted" style={{ marginBottom: 0 }}>{t("ai.chat_locked")}</p>}
      <p className="small muted" style={{ marginBottom: 0 }}>{t("ai.chat_rules")}</p>
    </Card>
  );
}

export default function Assistant() {
  const { t, tx } = useI18n();
  const { status } = useAiReady();
  return (
    <>
      <PageHeader title={t("ai.page_title")} question={t("q.ai")} desc={t("ai.page_desc")} />
      {status && !status.configured && !status.demo && (
        <Accordion title={t("ai.setup_title")} open>
          <ol style={{ paddingLeft: 20, display: "grid", gap: 8, margin: 0 }}>
            <li>{tx("ai.setup1")}</li>
            <li>{tx("ai.setup2")}<pre className="sent">{"OPENAI_API_KEY=sk-...\nNCU_GIFT_LLM_MODEL=gpt-6-luna"}</pre></li>
            <li>{tx("ai.setup3")}</li>
            <li>{tx("ai.setup4")}</li>
          </ol>
          <p className="small muted">{t("ai.setup_demo")}</p>
        </Accordion>
      )}
      <Chat />
    </>
  );
}
