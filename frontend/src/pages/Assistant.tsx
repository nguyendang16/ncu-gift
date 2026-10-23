import { useSearchParams } from "react-router-dom";
import { AgentChat } from "../components/AgentChat";
import { Accordion, Card, PageHeader } from "../components/ui";
import { useI18n } from "../i18n";
import { useAiReady } from "../components/AiParts";

export default function Assistant() {
  const { t, tx } = useI18n();
  const { status } = useAiReady();
  const [qs] = useSearchParams();
  const initialId = qs.get("c") ? Number(qs.get("c")) : undefined;
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
      <Card ai icon="chat" title={t("ai.chat_title")} sub={t("ai.chat_sub")}>
        <AgentChat initialId={initialId} />
      </Card>
    </>
  );
}
