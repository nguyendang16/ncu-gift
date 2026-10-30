import { Fragment, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { Link, useLocation } from "react-router-dom";
import { useConversations, useDeleteConversation } from "../../api/hooks";
import type { AgentStep } from "../../api/types";
import { useI18n } from "../../i18n";
import type { Key } from "../../i18n/en";
import { AiOffHint, DemoNotice, useAiReady } from "../AiParts";
import { Icon, type IconName } from "../ui";
import { RobotMark } from "./RobotMark";
import { type Turn, useAgentChat } from "./useAgentChat";
import { Visual } from "./Visuals";

export type Chat = ReturnType<typeof useAgentChat>;

/* ------------------------------------------------------------------ answer text */
/** Plain text from the model: paragraphs, bullet lines, **bold**, and [n] source marks shown as small numbered chips. */
function inline(text: string, scope: string, onCite: (n: number) => void): ReactNode {
  return text.split(/(\*\*[^*]+\*\*|\[\d{1,2}\])/g).map((part, i) => {
    if (part.startsWith("**") && part.endsWith("**") && part.length > 4) return <b key={i}>{part.slice(2, -2)}</b>;
    const m = /^\[(\d{1,2})\]$/.exec(part);
    if (m) return <button key={i} type="button" className="cite" aria-label={`Source ${m[1]}`} onClick={() => onCite(Number(m[1]))}>{m[1]}</button>;
    return <Fragment key={`${scope}${i}`}>{part}</Fragment>;
  });
}

function Prose({ text, scope, onCite }: { text: string; scope: string; onCite: (n: number) => void }) {
  const out: ReactNode[] = [];
  let list: { kind: "ul" | "ol"; items: string[] } | null = null;
  const flush = () => {
    if (!list) return;
    const items = list.items.map((x, i) => <li key={i}>{inline(x, scope, onCite)}</li>);
    out.push(list.kind === "ol" ? <ol key={`l${out.length}`}>{items}</ol> : <ul key={`l${out.length}`}>{items}</ul>);
    list = null;
  };
  for (const raw of text.split("\n")) {
    const line = raw.trim();
    const m = /^([•\-*]|\d{1,2}[.)])\s+(.*)$/.exec(line);
    if (m) {
      const kind = /^\d/.test(m[1]) ? "ol" : "ul";
      if (list && list.kind !== kind) flush();
      list = list ?? { kind, items: [] };
      list.items.push(m[2]);
    } else { flush(); if (line) out.push(<p key={`p${out.length}`}>{inline(line, scope, onCite)}</p>); }
  }
  flush();
  return <div className="cp-prose">{out}</div>;
}

/* ------------------------------------------------------------------ evidence */
function TableCard({ step }: { step: AgentStep }) {
  const { t } = useI18n();
  const [all, setAll] = useState(false);
  const tb = step.table;
  if (!tb) return null;
  const rows = all ? tb.rows : tb.rows.slice(0, 5);
  return (
    <figure className="vis tbl">
      <figcaption>{step.title}{step.args_text && <span className="muted"> · {step.args_text}</span>}</figcaption>
      <div className="scroll"><table className="t">
        <thead><tr>{tb.columns.map((c) => <th key={c}>{c}</th>)}</tr></thead>
        <tbody>{rows.map((r, i) => <tr key={i}>{r.map((v, j) => <td key={j} className={j === 0 ? "mono" : ""}>{String(v)}</td>)}</tr>)}</tbody>
      </table></div>
      {tb.rows.length > 5 && <button className="cp-more" onClick={() => setAll(!all)}>{all ? t("ai.show_less") : t("ai.show_all", { n: tb.rows.length })}</button>}
    </figure>
  );
}

function Sources({ steps, open, setOpen }: { steps: AgentStep[]; open: number | null; setOpen: (n: number | null) => void }) {
  const { t } = useI18n();
  if (steps.length === 0) return null;
  const cur = steps.find((s) => s.n === open);
  return (
    <div className="cp-sources">
      <span className="cp-l">{t("ai.sources")}</span>
      {steps.map((s) => (
        <button key={s.n} type="button" className={`src ${open === s.n ? "on" : ""} ${s.ok ? "" : "bad"}`} aria-expanded={open === s.n} onClick={() => setOpen(open === s.n ? null : s.n)}>
          <i>{s.n}</i>{s.title}
        </button>
      ))}
      {cur && (
        <div className="src-detail" role="region">
          <b>{cur.title}</b>{cur.args_text && <span className="muted"> · {cur.args_text}</span>}
          <p>{cur.summary}</p>
        </div>
      )}
    </div>
  );
}

function GoRow({ steps, onNavigate }: { steps: AgentStep[]; onNavigate?: () => void }) {
  const seen = new Set<string>();
  const links = steps.flatMap((s) => s.links ?? []).filter((l) => (seen.has(l.label) ? false : (seen.add(l.label), true)));
  if (links.length === 0) return null;
  return (
    <div className="cp-go">
      {links.map((l) => <Link key={l.to} className="chip" to={l.to} onClick={onNavigate}>{l.label}<Icon name="arrow" size={14} /></Link>)}
    </div>
  );
}

/* ------------------------------------------------------------------ one exchange */
function Working({ turn }: { turn: Turn }) {
  const { t } = useI18n();
  const line = turn.phase === "checking" ? t("ai.ph_checking") : turn.steps.length ? t("ai.ph_writing") : t("ai.ph_choosing");
  return (
    <div className="cp-working" aria-live="polite">
      {turn.steps.map((s) => <div key={s.n} className="done"><Icon name="check" size={14} />{s.title}{s.args_text && <span className="muted"> · {s.args_text}</span>}</div>)}
      <div className="now"><span className="dots"><i /><i /><i /></span>{line}</div>
    </div>
  );
}

const plainText = (s: string) => s.replace(/\[\d{1,2}\]/g, "").replace(/\*\*/g, "");

function TurnView({ turn, chat, onNavigate }: { turn: Turn; chat: Chat; onNavigate?: () => void }) {
  const { t } = useI18n();
  const [src, setSrc] = useState<number | null>(null);
  const [copied, setCopied] = useState(false);
  const refs = useRef<HTMLDivElement>(null);
  const cite = (n: number) => { setSrc(n); refs.current?.querySelector(".cp-sources")?.scrollIntoView({ behavior: "smooth", block: "nearest" }); };
  const v = turn.verification;
  return (
    <div className="cp-turn">
      <div className="cp-user"><span>{turn.q}</span></div>
      <div className="cp-ai" ref={refs}>
        <span className="cp-av" aria-hidden="true"><RobotMark /></span>
        <div className="cp-body">
          {turn.status === "working" && <Working turn={turn} />}
          {turn.status === "error" && <div className="cp-err" role="alert"><Icon name="risk" size={16} /><div>{turn.error?.message}{(turn.error as { code?: string } | undefined)?.code === "ai_blocked" && <> <Link to="/ai">{t("ai.open_settings")}</Link></>}</div></div>}
          {turn.status === "done" && (
            <>
              <Prose text={turn.answer} scope={turn.key} onCite={cite} />
              {turn.steps.map((s) => <Visual key={`v${s.n}`} step={s} />)}
              {turn.steps.map((s) => <TableCard key={`t${s.n}`} step={s} />)}
              <GoRow steps={turn.steps} onNavigate={onNavigate} />
              <Sources steps={turn.steps} open={src} setOpen={setSrc} />
              <div className="cp-actions">
                <button className="ib" title={copied ? t("ai.copied") : t("ai.copy")} aria-label={t("ai.copy")} onClick={() => { void navigator.clipboard?.writeText(plainText(turn.answer)); setCopied(true); setTimeout(() => setCopied(false), 1500); }}><Icon name={copied ? "check" : "copy"} size={15} /></button>
                <button className={`ib ${turn.feedback === 1 ? "on" : ""}`} title={t("ai.useful")} aria-label={t("ai.useful")} aria-pressed={turn.feedback === 1} disabled={!turn.messageId} onClick={() => chat.rate(turn.key, 1)}><Icon name="up" size={15} /></button>
                <button className={`ib ${turn.feedback === -1 ? "on bad" : ""}`} title={t("ai.not_useful")} aria-label={t("ai.not_useful")} aria-pressed={turn.feedback === -1} disabled={!turn.messageId} onClick={() => chat.rate(turn.key, -1)}><Icon name="down" size={15} /></button>
                <button className="ib" title={t("ai.retry")} aria-label={t("ai.retry")} disabled={chat.busy} onClick={() => chat.send(turn.q)}><Icon name="retry" size={15} /></button>
                <span className="grow" />
                {turn.demo && <span className="cp-tag">{t("ai.demo_tag")}</span>}
                {v && v.checked > 0 && (v.ok
                  ? <span className="cp-ver" title={t("ai.verified_hint")}><Icon name="shield" size={14} />{t("ai.verified", { n: v.checked })}</span>
                  : <span className="cp-ver warn" title={v.unverified.join(", ")}><Icon name="risk" size={14} />{t("ai.unverified", { list: v.unverified.join(", ") })}</span>)}
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ empty state */
const ICONS: IconName[] = ["phone", "strategy", "chart", "route"];
function suggestionKeys(path: string): Key[] {
  if (path.startsWith("/risk") || path.startsWith("/matching") || path.startsWith("/journey")) return ["sg.d1", "sg.d2", "sg.d3", "sg.d4"];
  if (path.startsWith("/strategy") || path.startsWith("/briefs")) return ["sg.p1", "sg.p2", "sg.p3", "sg.p4"];
  if (path.startsWith("/data") || path.startsWith("/roll")) return ["sg.x1", "sg.x2", "sg.x3", "sg.x4"];
  return ["sg.o1", "sg.o2", "sg.o3", "sg.o4"];
}

function Empty({ chat, ready, wide }: { chat: Chat; ready: boolean; wide?: boolean }) {
  const { t } = useI18n();
  const loc = useLocation();
  const keys = suggestionKeys(loc.pathname);
  return (
    <div className={`cp-empty ${wide ? "wide" : ""}`}>
      <span className="cp-logo"><RobotMark /></span>
      <h2>{t("ai.hello")}</h2>
      <p>{t("ai.hello_sub")}</p>
      <div className="cp-cards">
        {keys.map((k, i) => (
          <button key={k} className="cp-card" disabled={!ready} onClick={() => chat.send(t(k))}><Icon name={ICONS[i]} size={18} /><span>{t(k)}</span></button>
        ))}
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ composer */
function Composer({ chat, ready }: { chat: Chat; ready: boolean }) {
  const { t } = useI18n();
  const [text, setText] = useState("");
  const ta = useRef<HTMLTextAreaElement>(null);
  useEffect(() => { const el = ta.current; if (el) { el.style.height = "auto"; el.style.height = `${Math.min(el.scrollHeight, 140)}px`; } }, [text]);
  const go = () => { if (text.trim() && ready && !chat.busy) { chat.send(text); setText(""); } };
  return (
    <form className="cp-composer" onSubmit={(e) => { e.preventDefault(); go(); }}>
      <textarea ref={ta} rows={1} value={text} disabled={!ready} placeholder={ready ? t("ai.ask_placeholder") : t("ai.chat_locked")} aria-label={t("ai.ask_placeholder")}
        onChange={(e) => setText(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) { e.preventDefault(); go(); } }} />
      <button type="submit" className="send" aria-label={t("ai.send")} disabled={!ready || chat.busy || !text.trim()}><Icon name="up" size={18} /></button>
    </form>
  );
}

export function ChatBody({ chat, onNavigate, wide }: { chat: Chat; onNavigate?: () => void; wide?: boolean }) {
  const { t } = useI18n();
  const { ready } = useAiReady();
  const end = useRef<HTMLDivElement>(null);
  useEffect(() => { end.current?.scrollIntoView({ behavior: "smooth", block: "end" }); }, [chat.turns.length, chat.turns[chat.turns.length - 1]?.steps.length, chat.turns[chat.turns.length - 1]?.status]);
  return (
    <div className="cp-chat">
      <div className="cp-scroll">
        <DemoNotice />
        <AiOffHint />
        {chat.turns.length === 0 && !chat.loading ? <Empty chat={chat} ready={ready} wide={wide} /> : (
          <div className="cp-thread">
            {chat.loading !== undefined && <div className="cp-ai"><span className="cp-av"><RobotMark /></span><div className="cp-body muted">{t("ui.loading")}</div></div>}
            {chat.turns.map((x) => <TurnView key={x.key} turn={x} chat={chat} onNavigate={onNavigate} />)}
            <div ref={end} />
          </div>
        )}
      </div>
      <Composer chat={chat} ready={ready} />
      <p className="cp-note">{t("ai.note")}</p>
    </div>
  );
}

/* ------------------------------------------------------------------ history */
function dayGroup(iso: string, t: ReturnType<typeof useI18n>["t"]): string {
  const d = new Date(iso + (iso.endsWith("Z") ? "" : "Z"));
  const days = Math.floor((Date.now() - d.getTime()) / 86_400_000);
  return days < 1 ? t("ai.today") : days < 2 ? t("ai.yesterday") : days < 8 ? t("ai.week") : t("ai.earlier");
}

export function HistoryList({ chat, onPicked }: { chat: Chat; onPicked?: () => void }) {
  const { t } = useI18n();
  const q = useConversations();
  const del = useDeleteConversation();
  const [find, setFind] = useState("");
  const rows = useMemo(() => (q.data ?? []).filter((r) => r.title.toLowerCase().includes(find.trim().toLowerCase())), [q.data, find]);
  const groups = useMemo(() => {
    const g = new Map<string, typeof rows>();
    for (const r of rows) { const k = dayGroup(r.updated_at, t); g.set(k, [...(g.get(k) ?? []), r]); }
    return [...g];
  }, [rows, t]);
  return (
    <div className="cp-hist">
      <label className="cp-search"><Icon name="search" size={16} /><input value={find} onChange={(e) => setFind(e.target.value)} placeholder={t("ai.search_history")} aria-label={t("ai.search_history")} /></label>
      {groups.length === 0 && <p className="muted small" style={{ padding: "6px 4px" }}>{q.data?.length ? t("ai.no_match") : t("ai.history_empty")}</p>}
      {groups.map(([name, list]) => (
        <div key={name}>
          <div className="cp-grp">{name}</div>
          {list.map((r) => (
            <div key={r.id} className={`cp-item ${r.id === chat.convId ? "on" : ""}`}>
              <button className="pick" onClick={() => { void chat.open(r.id); onPicked?.(); }}>{r.title}</button>
              <button className="del" aria-label={t("ai.history_delete")} title={t("ai.history_delete")} onClick={() => { if (r.id === chat.convId) chat.fresh(); del.mutate(r.id); }}><Icon name="trash" size={15} /></button>
            </div>
          ))}
        </div>
      ))}
      {(q.data?.length ?? 0) > 0 && <button className="cp-clear" onClick={() => { if (window.confirm(t("ai.history_clear_confirm"))) { chat.fresh(); del.mutate(undefined); } }}>{t("ai.history_clear")}</button>}
      <p className="small muted" style={{ margin: "8px 4px 0" }}>{t("ai.history_local")}</p>
    </div>
  );
}
