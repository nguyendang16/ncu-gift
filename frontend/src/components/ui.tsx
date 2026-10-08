import type { UseQueryResult } from "@tanstack/react-query";
import { useEffect, useRef, useState, type ReactNode } from "react";
import { ApiError } from "../api/client";
import { useI18n } from "../i18n";
import type { Key } from "../i18n/en";

/* ------------------------------------------------------------------ icons */
const PATHS = {
  overview: "M3 3h8v8H3z M13 3h8v5h-8z M13 10h8v11h-8z M3 13h8v8H3z",
  journey: "M4 18c4 0 4-12 8-12s4 12 8 12",
  risk: "M12 3l9 16H3z M12 10v4 M12 17h.01",
  match: "M16 10a4 4 0 1 0-8 0 M4 21c0-4 3.5-6 8-6s8 2 8 6",
  brief: "M7 3h7l4 4v14H7z M14 3v4h4 M9.5 12h5 M9.5 16h5",
  strategy: "M4 8h9 M17 8h3 M4 16h3 M11 16h9 M13 6v4 M7 14v4",
  roll: "M5 5h14 M5 10h14 M5 15h9 M5 20h6",
  data: "M4 6c0-1.7 3.6-3 8-3s8 1.3 8 3-3.6 3-8 3-8-1.3-8-3z M4 6v6c0 1.7 3.6 3 8 3s8-1.3 8-3V6 M4 12v6c0 1.7 3.6 3 8 3s8-1.3 8-3v-6",
  ai: "M12 3l1.9 5.1L19 10l-5.1 1.9L12 17l-1.9-5.1L5 10l5.1-1.9z M19 16l.8 2.2L22 19l-2.2.8L19 22l-.8-2.2L16 19l2.2-.8z",
  trend: "M3 17l6-6 4 4 8-8 M15 7h6v6",
  pie: "M12 3v9h9 M20.5 14a9 9 0 1 1-10.5-10.5",
  route: "M6 19a2 2 0 1 0 0-4 2 2 0 0 0 0 4z M18 9a2 2 0 1 0 0-4 2 2 0 0 0 0 4z M8 17h4a4 4 0 0 0 4-4V9",
  phone: "M5 4h4l2 5-2.5 1.5a11 11 0 0 0 5 5L15 13l5 2v4a2 2 0 0 1-2 2A16 16 0 0 1 3 6a2 2 0 0 1 2-2",
  people: "M9 11a3 3 0 1 0 0-6 3 3 0 0 0 0 6z M2 20c0-3.3 3.1-5 7-5s7 1.7 7 5 M17 11a3 3 0 1 0 0-6 M18 15c2.5.4 4 1.8 4 4",
  calendar: "M4 6h16v14H4z M4 10h16 M8 3v4 M16 3v4",
  money: "M12 3v18 M16.5 7.5C15.5 6.5 14 6 12 6c-2.5 0-4 1.2-4 3s1.5 2.5 4 3 4 1.2 4 3-1.5 3-4 3c-2 0-3.5-.5-4.5-1.5",
  gift: "M4 11h16v9H4z M3 7h18v4H3z M12 7v13 M12 7c-1.5-3.5-5-3-5-1 0 1.5 2 1 5 1z M12 7c1.5-3.5 5-3 5-1 0 1.5-2 1-5 1z",
  check: "M5 12l5 5 9-10",
  info: "M12 8h.01 M11 12h1v5h1 M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18z",
  chat: "M4 5h16v11H9l-5 4z",
  shield: "M12 3l8 3v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6z",
  repeat: "M17 2l4 4-4 4 M3 11V9a3 3 0 0 1 3-3h15 M7 22l-4-4 4-4 M21 13v2a3 3 0 0 1-3 3H3",
  send: "M4 12l16-8-6 16-3-7z",
  chart: "M4 20V10 M10 20V4 M16 20v-8 M22 20H2",
} as const;
export type IconName = keyof typeof PATHS;
export function Icon({ name, size = 20 }: { name: IconName; size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d={PATHS[name]} />
    </svg>
  );
}

/* ------------------------------------------------------------------ page chrome */
export function PageHeader({ title, desc, question, children }: { title: string; desc?: string; question?: string; children?: ReactNode }) {
  return (
    <div className="page-h rise">
      <div>
        {question && <div className="q-chip"><Icon name="info" size={15} />{question}</div>}
        <h1>{title}</h1>
        {desc && <p>{desc}</p>}
      </div>
      {children && <div className="controls">{children}</div>}
    </div>
  );
}

export function Section({ title, desc, id, children }: { title: string; desc?: string; id?: string; children: ReactNode }) {
  return (
    <section id={id} aria-labelledby={id ? `${id}-h` : undefined}>
      <div className="section-h"><h2 id={id ? `${id}-h` : undefined}>{title}</h2>{desc && <p>{desc}</p>}</div>
      {children}
    </section>
  );
}

export function Card({ title, sub, right, icon, ai, help, children, className = "" }: { title?: string; sub?: string; right?: ReactNode; icon?: IconName; ai?: boolean; help?: Key; children: ReactNode; className?: string }) {
  return (
    <section className={`card ${ai ? "ai" : ""} ${className}`}>
      {(title || right) && (
        <div className="card-h">
          <div className="ttl">
            {icon && <span className="ico" style={ai ? { background: "var(--ai-weak)", color: "var(--ai-2)" } : undefined}><Icon name={icon} size={19} /></span>}
            <div>
              {title && <h2>{title}{help && <InfoTip k={help} />}</h2>}
              {sub && <div className="sub">{sub}</div>}
            </div>
          </div>
          {right}
        </div>
      )}
      {children}
    </section>
  );
}

export function Accordion({ title, children, open }: { title: string; children: ReactNode; open?: boolean }) {
  return (
    <details className="acc" open={open}>
      <summary>{title}</summary>
      <div className="body">{children}</div>
    </details>
  );
}

/** A "?" next to a technical term. Click or keyboard to open; the text is plain language. */
export function InfoTip({ k }: { k: Key }) {
  const { t, tx } = useI18n();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLSpanElement>(null);
  useEffect(() => {
    if (!open) return;
    const close = (e: MouseEvent | KeyboardEvent) => {
      if (e instanceof KeyboardEvent ? e.key === "Escape" : !ref.current?.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", close);
    document.addEventListener("keydown", close);
    return () => { document.removeEventListener("mousedown", close); document.removeEventListener("keydown", close); };
  }, [open]);
  return (
    <span className="tip" ref={ref}>
      <button type="button" aria-expanded={open} aria-label={t("ui.explain")} onClick={() => setOpen(!open)}>?</button>
      {open && <span className="pop" role="note">{tx(k)}</span>}
    </span>
  );
}

/* ------------------------------------------------------------------ numbers */
export function Sparkline({ values, color = "#0d9488" }: { values: number[]; color?: string }) {
  if (values.length < 2) return null;
  const w = 96, h = 36, pad = 4;
  const min = Math.min(...values), max = Math.max(...values), span = max - min || 1;
  const pts = values.map((v, i) => [pad + (i * (w - 2 * pad)) / (values.length - 1), h - pad - ((v - min) / span) * (h - 2 * pad)]);
  const line = pts.map((p) => p.join(",")).join(" ");
  const last = pts[pts.length - 1];
  return (
    <svg className="spark" width={w} height={h} viewBox={`0 0 ${w} ${h}`} aria-hidden="true">
      <polygon points={`${pts[0][0]},${h} ${line} ${last[0]},${h}`} fill={color} opacity="0.12" />
      <polyline points={line} fill="none" stroke={color} strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" />
      <circle cx={last[0]} cy={last[1]} r="3.4" fill={color} />
    </svg>
  );
}

export function StatCard({ icon, label, value, sub, spark, tone, help }: { icon: IconName; label: string; value: ReactNode; sub?: ReactNode; spark?: number[]; tone?: "amber" | "indigo"; help?: Key }) {
  const color = tone === "amber" ? "#f59e0b" : tone === "indigo" ? "#4f46e5" : "#0d9488";
  return (
    <div className={`stat ${tone ?? ""}`}>
      <div className="top"><span className="ico"><Icon name={icon} size={18} /></span><span className="l">{label}{help && <InfoTip k={help} />}</span></div>
      <div className="v">{value}</div>
      {spark && <Sparkline values={spark} color={color} />}
      {sub && <div className="s">{sub}</div>}
    </div>
  );
}

export function Kpi({ label, value, sub, tone, help }: { label: string; value: ReactNode; sub?: ReactNode; tone?: "accent" | "warn"; help?: Key }) {
  return (
    <div className={`kpi ${tone ?? ""}`}>
      <div className="l">{label}{help && <InfoTip k={help} />}</div>
      <div className="v">{value}</div>
      {sub && <div className="s">{sub}</div>}
    </div>
  );
}

export function Delta({ v }: { v: number | null | undefined }) {
  const { fmt } = useI18n();
  if (v == null) return <span className="muted">–</span>;
  return <span className={`delta ${v >= 0 ? "up" : "down"}`}>{fmt.signedPct(v)}</span>;
}

/* ------------------------------------------------------------------ feedback */
export function Notice({ tone = "info", title, children }: { tone?: "info" | "warn" | "block" | "ok" | "ai"; title?: string; children?: ReactNode }) {
  return (
    <div className={`notice ${tone}`} role={tone === "block" ? "alert" : "note"}>
      <div>
        {title && <b>{title}</b>}
        {title && children ? " " : null}
        {children}
      </div>
    </div>
  );
}

export function Pill({ status }: { status: string }) {
  const { t } = useI18n();
  return <span className={`pill ${status === "available" ? "ok" : status === "caveat" ? "caveat" : "blocked"}`}>{t(`status.${status}` as Key)}</span>;
}

export const AiBadge = () => <span className="badge-ai"><Icon name="ai" size={12} />AI</span>;

export function Loading({ label }: { label?: string }) {
  const { t } = useI18n();
  return (
    <div className="loading" role="status">
      <div className="skeleton" style={{ height: 14, width: 180, margin: "0 auto 10px" }} />
      {label ?? t("ui.loading")}
    </div>
  );
}

export function EmptyState({ icon, title, children }: { icon: IconName; title: string; children?: ReactNode }) {
  return <div className="empty"><div style={{ color: "var(--muted)", marginBottom: 8 }}><Icon name={icon} size={34} /></div><h3>{title}</h3>{children && <div className="small">{children}</div>}</div>;
}

/** Missing information is reported in the staff's own style, never papered over. */
export function ErrorView({ error, retry }: { error: Error; retry?: () => void }) {
  const { t } = useI18n();
  if (error instanceof ApiError && error.code === "insufficient_data") {
    return (
      <Notice tone="block" title={t("ui.insufficient_title")}>
        {error.message} <span className="muted">{t("ui.insufficient_hint")}</span>
      </Notice>
    );
  }
  if (error instanceof ApiError && error.code === "ai_blocked") {
    return <Notice tone="ai" title={t("ai.blocked_title")}>{error.message}</Notice>;
  }
  return (
    <Notice tone="block" title={t("ui.error_title")}>
      {error.message}{" "}
      {retry && <button className="btn" onClick={retry}>{t("ui.try_again")}</button>}
    </Notice>
  );
}

export function Q<T>({ q, children, label }: { q: UseQueryResult<T, Error>; children: (d: T) => ReactNode; label?: string }) {
  if (q.isPending) return <Loading label={label} />;
  if (q.isError) return <ErrorView error={q.error} retry={() => q.refetch()} />;
  return <>{children(q.data)}</>;
}

export function Seg<T extends string>({ value, options, onChange, label }: { value: T; options: { v: T; l: string }[]; onChange: (v: T) => void; label: string }) {
  return (
    <div className="seg" role="group" aria-label={label}>
      {options.map((o) => (
        <button key={o.v} aria-pressed={value === o.v} onClick={() => onChange(o.v)}>{o.l}</button>
      ))}
    </div>
  );
}

export const Bar = ({ value, max = 1, amber }: { value: number; max?: number; amber?: boolean }) => (
  <div className={`bar ${amber ? "amber" : ""}`} aria-hidden="true">
    <i style={{ width: `${Math.max(0, Math.min(100, (value / (max || 1)) * 100))}%` }} />
  </div>
);

export function Tabs<T extends string>({ value, tabs, onChange }: { value: T; tabs: { v: T; l: string }[]; onChange: (v: T) => void }) {
  return (
    <div className="tabs" role="tablist">
      {tabs.map((tb) => (
        <button key={tb.v} role="tab" aria-selected={value === tb.v} onClick={() => onChange(tb.v)}>{tb.l}</button>
      ))}
    </div>
  );
}

export function useDebounced<T>(value: T, ms = 250): T {
  const [v, setV] = useState(value);
  useEffect(() => { const t = setTimeout(() => setV(value), ms); return () => clearTimeout(t); }, [value, ms]);
  return v;
}
