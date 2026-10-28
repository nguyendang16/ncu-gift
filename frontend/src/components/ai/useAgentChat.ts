import { useQueryClient } from "@tanstack/react-query";
import { useCallback, useState } from "react";
import { api, ApiError } from "../../api/client";
import type { AgentStep, ConversationOut, NumberCheck } from "../../api/types";
import { useApp } from "../../context/AppContext";
import { streamAgent } from "../../lib/agentStream";

export type Turn = {
  key: string;
  q: string;
  answer: string;
  steps: AgentStep[];
  verification?: NumberCheck | null;
  demo: boolean;
  messageId?: number;
  feedback: number;
  status: "working" | "done" | "error";
  phase: "thinking" | "checking";
  error?: Error;
};

const turnsOf = (c: ConversationOut): Turn[] => {
  const out: Turn[] = [];
  let q = "";
  for (const m of c.messages) {
    if (m.role === "user") q = m.text;
    else out.push({ key: `m${m.id}`, q, answer: m.text, steps: m.steps ?? [], verification: m.verification, demo: m.demo, messageId: m.id, feedback: m.feedback ?? 0, status: "done", phase: "thinking" });
  }
  return out;
};

/** One conversation with the analyst: sending (with live progress), reopening a saved one, rating an answer. */
export function useAgentChat(initialId?: number) {
  const { datasetId, settings } = useApp();
  const qc = useQueryClient();
  const [convId, setConvId] = useState<number | undefined>(initialId);
  const [turns, setTurns] = useState<Turn[]>([]);
  const [loading, setLoading] = useState<number | undefined>(initialId);
  const busy = turns.some((x) => x.status === "working");

  const patch = useCallback((key: string, f: (t: Turn) => Turn) => setTurns((p) => p.map((x) => (x.key === key ? f(x) : x))), []);

  const send = useCallback(async (question: string) => {
    const q = question.trim();
    if (!q || busy) return;
    const key = `t${Date.now()}`;
    const history = turns.filter((x) => x.status === "done").slice(-3).map((x) => ({ question: x.q, answer: x.answer }));
    setTurns((p) => [...p, { key, q, answer: "", steps: [], demo: false, feedback: 0, status: "working", phase: "thinking" }]);
    try {
      await streamAgent({ dataset_id: datasetId, question: q, conversation_id: convId, history, exceptional_threshold: settings.exceptional, large_threshold: settings.large }, (e) => {
        if (e.type === "thinking") patch(key, (x) => ({ ...x, phase: "thinking" }));
        else if (e.type === "checking") patch(key, (x) => ({ ...x, phase: "checking" }));
        else if (e.type === "step") patch(key, (x) => ({ ...x, steps: [...x.steps, e.step] }));
        else if (e.type === "answer") {
          const r = e.result;
          setConvId(r.conversation_id ?? undefined);
          patch(key, (x) => ({ ...x, answer: r.answer, steps: r.steps, verification: r.verification, demo: r.demo, messageId: r.message_id ?? undefined, status: "done" }));
        } else if (e.type === "error") {
          patch(key, (x) => ({ ...x, status: "error", error: new ApiError(e.code === "ai_blocked" ? 403 : 502, e.message, e.code) }));
        }
      });
    } catch (err) {
      patch(key, (x) => (x.status === "working" ? { ...x, status: "error", error: err as Error } : x));
    } finally {
      qc.invalidateQueries({ queryKey: ["ai-status"] });
      qc.invalidateQueries({ queryKey: ["ai-conversations"] });
    }
  }, [busy, turns, datasetId, convId, settings.exceptional, settings.large, patch, qc]);

  const open = useCallback(async (id: number) => {
    setLoading(id);
    try {
      const c = await api<ConversationOut>(`/api/ai/conversations/${id}`);
      setTurns(turnsOf(c)); setConvId(id);
    } finally { setLoading(undefined); }
  }, []);

  const fresh = useCallback(() => { setConvId(undefined); setTurns([]); setLoading(undefined); }, []);

  const rate = useCallback(async (key: string, value: 1 | -1) => {
    const cur = turns.find((x) => x.key === key);
    if (!cur?.messageId) return;
    const next = cur.feedback === value ? 0 : value;
    patch(key, (x) => ({ ...x, feedback: next }));
    try { await api(`/api/ai/messages/${cur.messageId}/feedback`, { body: { value: next } }); } catch { patch(key, (x) => ({ ...x, feedback: cur.feedback })); }
  }, [turns, patch]);

  return { turns, convId, loading, busy, send, open, fresh, rate };
}
