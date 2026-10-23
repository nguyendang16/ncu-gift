import { useEffect, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { useI18n } from "../i18n";
import { AgentChat } from "./AgentChat";
import { useAiReady } from "./AiParts";
import { Icon } from "./ui";

/** The round AI button at the bottom right of every page, and the panel it opens. The full page lives at /ai. */
export function AssistantDock() {
  const { t } = useI18n();
  const loc = useLocation();
  const { status } = useAiReady();
  const [open, setOpen] = useState(false);
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") setOpen(false); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open]);
  if (loc.pathname === "/ai") return null;
  const dot = status?.ready ? (status.demo ? "demo" : "on") : "";
  return (
    <>
      {open && (
        <section className="dock-panel" role="dialog" aria-label={t("ai.dock_title")}>
          <header className="dock-h">
            <span className="ico"><Icon name="ai" size={18} /></span>
            <b>{t("ai.dock_title")}</b>
            <span className="spacer" />
            <Link className="dock-ib" to="/ai" onClick={() => setOpen(false)} title={t("ai.dock_full")} aria-label={t("ai.dock_full")}>⤢</Link>
            <button className="dock-ib" onClick={() => setOpen(false)} title={t("ai.dock_close")} aria-label={t("ai.dock_close")}>×</button>
          </header>
          <div className="dock-body"><AgentChat compact onNavigate={() => setOpen(false)} /></div>
        </section>
      )}
      <button className={`dock-fab ${open ? "open" : ""}`} onClick={() => setOpen(!open)} aria-expanded={open} aria-label={t("ai.dock_open")}>
        <Icon name="ai" size={22} /><span className="lbl">{t("ai.dock_open")}</span>{dot && <i className={`st ${dot}`} />}
      </button>
    </>
  );
}
