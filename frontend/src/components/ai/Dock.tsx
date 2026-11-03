import { useEffect, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { useI18n } from "../../i18n";
import { useAiReady } from "../AiParts";
import { Icon } from "../ui";
import { ChatBody, HistoryList } from "./Chat";
import { RobotMark } from "./RobotMark";
import { useAiDock } from "./dockContext";
import { useAgentChat } from "./useAgentChat";

function RobotHead() {
  return (
    <svg className="bot" viewBox="0 -1.2 32 32" aria-hidden="true">
      <g className="waves">
        <path className="wave w1" d="M12.2 4.8a3.8 3.8 0 0 0 7.6 0" />
        <path className="wave w2" d="M10.4 4.8a5.6 5.6 0 0 0 11.2 0" />
        <path className="wave w3" d="M8.6 4.8a7.4 7.4 0 0 0 14.8 0" />
        <path className="wave w4" d="M6.8 4.8a9.2 9.2 0 0 0 18.4 0" />
        <path className="wave w5" d="M5 4.8a11 11 0 0 0 22 0" />
      </g>
      <line x1="16" y1="6.2" x2="16" y2="8.2" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
      <circle className="bulb" cx="16" cy="4.8" r="1.65" fill="#fff3c4" stroke="currentColor" strokeWidth="1.5" />
      <rect x="2.3" y="12.4" width="3.1" height="5.4" rx="1.4" fill="currentColor" />
      <rect x="26.6" y="12.4" width="3.1" height="5.4" rx="1.4" fill="currentColor" />
      <rect x="5.2" y="8" width="21.6" height="18.4" rx="6.4" fill="#fff3c4" stroke="currentColor" strokeWidth="1.7" />
      <circle cx="12.1" cy="15.3" r="1.75" fill="currentColor" />
      <circle cx="19.9" cy="15.3" r="1.75" fill="currentColor" />
      <path d="M12.3 19.8c1.05 1.15 2.25 1.7 3.7 1.7s2.65-.55 3.7-1.7" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
    </svg>
  );
}

/** The panel on the right (like the side assistants in Microsoft Copilot and Google Workspace) and the round button that opens it. */
export function AiDock() {
  const { t } = useI18n();
  const loc = useLocation();
  const { status, ready } = useAiReady();
  const { open, wide, setOpen, setWide, pending, clear } = useAiDock();
  const chat = useAgentChat();
  const [view, setView] = useState<"chat" | "history">("chat");

  useEffect(() => {
    if (pending && ready && !chat.busy) { setView("chat"); void chat.send(pending.q); clear(); }
  }, [pending, ready, chat, clear]);
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") setOpen(false); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, setOpen]);

  if (loc.pathname === "/ai") return null;
  const dot = ready ? (status?.demo ? "demo" : "on") : "";
  if (!open) {
    return (
      <button className="cp-fab" onClick={() => setOpen(true)} aria-label={t("ai.dock_open")} title={`${t("ai.dock_open")}  (Ctrl/⌘ K)`}>
        <RobotHead />{dot && <i className={`st ${dot}`} />}
      </button>
    );
  }
  return (
    <aside className={`cp-panel ${wide ? "wide" : ""}`} role="complementary" aria-label={t("ai.dock_title")}>
      <header className="cp-head">
        <span className="cp-logo sm" aria-hidden="true"><RobotMark /></span>
        <b>{view === "history" ? t("ai.history") : t("ai.dock_title")}</b>
        <span className="grow" />
        <button className={`ib ${view === "history" ? "on" : ""}`} onClick={() => setView(view === "history" ? "chat" : "history")} title={t("ai.history")} aria-label={t("ai.history")}><Icon name="clock" size={17} /></button>
        <button className="ib" onClick={() => { chat.fresh(); setView("chat"); }} title={t("ai.new_chat")} aria-label={t("ai.new_chat")}><Icon name="plus" size={17} /></button>
        <button className="ib hide-sm" onClick={() => setWide(!wide)} title={wide ? t("ai.narrow") : t("ai.wider")} aria-label={wide ? t("ai.narrow") : t("ai.wider")}><Icon name="expand" size={16} /></button>
        <Link className="ib" to="/ai" onClick={() => setOpen(false)} title={t("ai.dock_full")} aria-label={t("ai.dock_full")}><Icon name="arrow" size={16} /></Link>
        <button className="ib" onClick={() => setOpen(false)} title={t("ai.dock_close")} aria-label={t("ai.dock_close")}><Icon name="close" size={17} /></button>
      </header>
      {view === "history"
        ? <div className="cp-pad"><HistoryList chat={chat} onPicked={() => setView("chat")} /></div>
        : <ChatBody chat={chat} wide={wide} onNavigate={() => { if (window.innerWidth < 1100) setOpen(false); }} />}
    </aside>
  );
}
