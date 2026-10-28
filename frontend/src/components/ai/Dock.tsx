import { useEffect, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { useI18n } from "../../i18n";
import { useAiReady } from "../AiParts";
import { Icon } from "../ui";
import { ChatBody, HistoryList } from "./Chat";
import { useAiDock } from "./dockContext";
import { useAgentChat } from "./useAgentChat";

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
        <Icon name="ai" size={20} /><span className="lbl">{t("ai.dock_open")}</span>{dot && <i className={`st ${dot}`} />}
      </button>
    );
  }
  return (
    <aside className={`cp-panel ${wide ? "wide" : ""}`} role="complementary" aria-label={t("ai.dock_title")}>
      <header className="cp-head">
        <span className="cp-logo sm" aria-hidden="true"><Icon name="ai" size={15} /></span>
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
