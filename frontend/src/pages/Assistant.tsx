import { useEffect } from "react";
import { useSearchParams } from "react-router-dom";
import { Accordion } from "../components/ui";
import { useAiReady } from "../components/AiParts";
import { ChatBody, HistoryList } from "../components/ai/Chat";
import { useAgentChat } from "../components/ai/useAgentChat";
import { useI18n } from "../i18n";

/** The analyst full screen: saved conversations on the left, the conversation in the middle (like the large assistants). */
export default function Assistant() {
  const { t, tx } = useI18n();
  const { status } = useAiReady();
  const [qs] = useSearchParams();
  const initial = qs.get("c") ? Number(qs.get("c")) : undefined;
  const chat = useAgentChat();
  useEffect(() => { if (initial) void chat.open(initial); }, [initial]);        // eslint-disable-line react-hooks/exhaustive-deps
  return (
    <div className="cp-page">
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
      <div className="cp-page-grid">
        <aside className="cp-page-side">
          <button className="cp-newbtn" onClick={() => chat.fresh()}>{t("ai.new_chat")}</button>
          <HistoryList chat={chat} />
        </aside>
        <section className="cp-page-main"><ChatBody chat={chat} wide /></section>
      </div>
    </div>
  );
}
