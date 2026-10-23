import { Fragment, useEffect, useRef, useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { useAgent, useConversation, useConversations, useDeleteConversation } from "../api/hooks";
import type { AgentStep, AiTurn, ConversationOut, NumberCheck } from "../api/types";
import { useApp } from "../context/AppContext";
import { useI18n } from "../i18n";
import type { Key } from "../i18n/en";
import { AiOffHint, DemoNotice, VerifyBadge, useAiReady } from "./AiParts";
import { EmptyState, ErrorView, Icon } from "./ui";

const SUGGESTED: Key[] = ["ai.q1", "ai.q2", "ai.q3", "ai.q4"];

export type Turn = { q: string; answer: string; steps: AgentStep[]; verification?: NumberCheck | null; demo: boolean };

/** Models sometimes wrap figures in **bold**; [n] marks the analysis a figure came from and is shown as a small numbered chip. */
function plain(text: string, scope: string): ReactNode {
  return text.split(/(\*\*[^*]+\*\*|\[\d{1,2}\])/g).map((part, i) => {
    if (part.startsWith("**") && part.endsWith("**") && part.length > 4) return <b key={i}>{part.slice(2, -2)}</b>;
    const m = /^\[(\d{1,2})\]$/.exec(part);
    if (m) {
      const id = `src-${scope}-${m[1]}`;
      return <a key={i} className="cite" href={`#${id}`} onClick={(e) => { e.preventDefault(); document.getElementById(id)?.scrollIntoView({ behavior: "smooth", block: "center" }); }}>{m[1]}</a>;
    }
    return <Fragment key={i}>{part}</Fragment>;
  });
}

function StepCard({ s, scope, onNavigate }: { s: AgentStep; scope: string; onNavigate?: () => void }) {
  const links = s.links ?? [];          // older saved answers and older servers have no links
  return (
    <div className={`step ${s.ok ? "" : "bad"}`} id={`src-${scope}-${s.n}`}>
      <div className="step-h"><span className="cite static">{s.n}</span><b>{s.title}</b>{s.args_text && <span className="muted small"> · {s.args_text}</span>}</div>
      <div className="small">{s.summary}</div>
      {s.table && (
        <div className="scroll"><table className="t">
          <thead><tr>{s.table.columns.map((c) => <th key={c}>{c}</th>)}</tr></thead>
          <tbody>{s.table.rows.map((r, i) => <tr key={i}>{r.map((v, j) => <td key={j} className={j === 0 ? "mono" : ""}>{String(v)}</td>)}</tr>)}</tbody>
        </table></div>
      )}
      {links.length > 0 && (
        <div className="step-links">
          {links.map((l) => <Link key={l.to} className="btn" to={l.to} onClick={onNavigate}>{l.label} →</Link>)}
        </div>
      )}
    </div>
  );
}

const turnsOf = (c: ConversationOut): Turn[] => {
  const out: Turn[] = [];
  let q = "";
  for (const m of c.messages) {
    if (m.role === "user") q = m.text;
    else out.push({ q, answer: m.text, steps: m.steps ?? [], verification: m.verification, demo: m.demo });
  }
  return out;
};

function History({ onPick, onClose, current }: { onPick: (id: number) => void; onClose: () => void; current?: number }) {
  const { t, lang } = useI18n();
  const q = useConversations();
  const del = useDeleteConversation();
  const rows = q.data ?? [];
  const when = (iso: string) => new Date(iso + (iso.endsWith("Z") ? "" : "Z")).toLocaleString(lang === "zh-TW" ? "zh-TW" : "en-GB", { dateStyle: "medium", timeStyle: "short" });
  return (
    <div className="hist">
      <div className="hist-h">
        <b>{t("ai.history")}</b>
        <span style={{ display: "flex", gap: 6 }}>
          {rows.length > 0 && <button className="btn" style={{ minHeight: 32, padding: "2px 10px" }} onClick={() => { if (window.confirm(t("ai.history_clear_confirm"))) del.mutate(undefined); }}>{t("ai.history_clear")}</button>}
          <button className="btn" style={{ minHeight: 32, padding: "2px 10px" }} onClick={onClose}>{t("ai.history_back")}</button>
        </span>
      </div>
      <p className="small muted" style={{ margin: "0 0 8px" }}>{t("ai.history_local")}</p>
      {rows.length === 0 && <p className="muted">{t("ai.history_empty")}</p>}
      {rows.map((r) => (
        <div key={r.id} className={`hist-row ${r.id === current ? "on" : ""}`}>
          <button className="hist-pick" onClick={() => onPick(r.id)}><b>{r.title}</b><span className="small muted">{when(r.updated_at)} · {t("ai.history_n", { n: Math.floor(r.n_messages / 2) })}</span></button>
          <button className="hist-del" aria-label={t("ai.history_delete")} title={t("ai.history_delete")} onClick={() => del.mutate(r.id)}>×</button>
        </div>
      ))}
    </div>
  );
}

/** The analyst conversation. Used on the AI page and in the floating panel; both save to the same history. */
export function AgentChat({ initialId, onNavigate, compact }: { initialId?: number; onNavigate?: () => void; compact?: boolean }) {
  const { datasetId, settings } = useApp();
  const { t } = useI18n();
  const { ready } = useAiReady();
  const ask = useAgent();
  const [convId, setConvId] = useState<number | undefined>(initialId);
  const [turns, setTurns] = useState<Turn[]>([]);
  const [text, setText] = useState("");
  const [view, setView] = useState<"chat" | "history">("chat");
  const [opening, setOpening] = useState<number | undefined>(initialId);
  const conv = useConversation(opening);
  const end = useRef<HTMLDivElement>(null);
  const scope = compact ? "d" : "p";

  useEffect(() => { end.current?.scrollIntoView({ behavior: "smooth", block: "nearest" }); }, [turns.length, ask.isPending]);
  useEffect(() => {
    if (opening !== undefined && conv.data && conv.data.id === opening) { setTurns(turnsOf(conv.data)); setConvId(opening); setOpening(undefined); setView("chat"); }
  }, [conv.data, opening]);

  const send = (q: string) => {
    q = q.trim();
    if (!q || !ready || ask.isPending) return;
    const history: AiTurn[] = turns.slice(-3).map((x) => ({ question: x.q, answer: x.answer }));
    ask.mutate({ dataset_id: datasetId, question: q, conversation_id: convId, history, exceptional_threshold: settings.exceptional, large_threshold: settings.large }, {
      onSuccess: (a) => {
        setConvId(a.conversation_id ?? convId);
        setTurns((p) => [...p, { q, answer: a.answer, steps: a.steps ?? [], verification: a.verification, demo: a.demo }]);
        setText("");
      },
    });
  };
  const fresh = () => { setConvId(undefined); setTurns([]); setView("chat"); setOpening(undefined); ask.reset(); };

  return (
    <div className={`agent ${compact ? "compact" : ""}`}>
      <div className="agent-bar">
        <button className="btn" onClick={fresh} disabled={turns.length === 0 && !convId}><Icon name="chat" size={15} />{t("ai.new_chat")}</button>
        <button className="btn" onClick={() => setView(view === "history" ? "chat" : "history")}><Icon name="calendar" size={15} />{t("ai.history")}</button>
      </div>
      {view === "history" ? (
        <History current={convId} onClose={() => setView("chat")} onPick={(id) => { setOpening(id); }} />
      ) : (
        <>
          <DemoNotice />
          <AiOffHint />
          <div className="chat" aria-live="polite">
            {turns.length === 0 && !ask.isPending && !opening && (
              <EmptyState icon="chat" title={t("ai.chat_empty")}>
                <div style={{ display: "flex", gap: 8, flexWrap: "wrap", justifyContent: "center", marginTop: 10 }}>
                  {SUGGESTED.map((k) => <button key={k} className="btn" disabled={!ready} onClick={() => send(t(k))}>{t(k)}</button>)}
                </div>
              </EmptyState>
            )}
            {opening !== undefined && <div className="msg bot muted">{t("ui.loading")}</div>}
            {turns.map((x, i) => (
              <div key={i} style={{ display: "grid", gap: 10 }}>
                <div className="msg user">{x.q}</div>
                <div className="msg bot">
                  {plain(x.answer, `${scope}${i}`)}
                  <div className="meta">
                    {x.verification && <VerifyBadge v={x.verification} />}
                    {x.demo && <span>{t("ai.by_demo")}</span>}
                  </div>
                  {x.steps.length > 0 && (
                    <div className="steps" style={{ whiteSpace: "normal" }}>
                      <div className="steps-h">{t("ai.how")}</div>
                      {x.steps.map((s) => <StepCard key={s.n} s={s} scope={`${scope}${i}`} onNavigate={onNavigate} />)}
                    </div>
                  )}
                </div>
              </div>
            ))}
            {ask.isPending && <div className="msg bot muted">{t("ai.working")}</div>}
            {ask.isError && <ErrorView error={ask.error} />}
            <div ref={end} />
          </div>
          <form className="chat-input" style={{ marginTop: 12 }} onSubmit={(e) => { e.preventDefault(); send(text); }}>
            <textarea value={text} placeholder={t("ai.chat_placeholder")} aria-label={t("ai.chat_placeholder")} disabled={!ready}
              onChange={(e) => setText(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(text); } }} />
            <button className="btn ai" type="submit" disabled={!ready || ask.isPending || !text.trim()}><Icon name="send" size={17} />{t("ai.send")}</button>
          </form>
          {!compact && <p className="small muted" style={{ marginBottom: 0 }}>{t("ai.chat_rules")}</p>}
        </>
      )}
    </div>
  );
}
