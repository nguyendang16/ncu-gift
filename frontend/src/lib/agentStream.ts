import { ApiError } from "../api/client";
import type { AgentOut, AgentStep } from "../api/types";
import { getLang } from "../i18n";

export type AgentEvent =
  | { type: "thinking"; n: number }
  | { type: "checking" }
  | { type: "step"; step: AgentStep }
  | { type: "answer"; result: AgentOut }
  | { type: "error"; code: string; message: string };

export type AgentBody = { dataset_id?: number; question: string; conversation_id?: number; history: { question: string; answer: string }[]; exceptional_threshold: number; large_threshold: number };

/** Reads the analyst's progress as it happens (one JSON object per line) and hands each event over; rejects with ApiError like any other call. */
export async function streamAgent(body: AgentBody, onEvent: (e: AgentEvent) => void): Promise<void> {
  const res = await fetch("/api/ai/agent/stream", { method: "POST", headers: { "Content-Type": "application/json", "Accept-Language": getLang() }, body: JSON.stringify(body) });
  if (!res.ok || !res.body) {
    let detail = res.statusText, code: string | undefined;
    try { const j = await res.json(); detail = typeof j.detail === "string" ? j.detail : detail; code = j.code; } catch { /* keep status text */ }
    throw new ApiError(res.status, detail, code);
  }
  const reader = res.body.getReader();
  const dec = new TextDecoder();
  let buf = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buf += dec.decode(value, { stream: true });
    let i: number;
    while ((i = buf.indexOf("\n")) >= 0) {
      const line = buf.slice(0, i).trim();
      buf = buf.slice(i + 1);
      if (line) onEvent(JSON.parse(line) as AgentEvent);
    }
  }
  if (buf.trim()) onEvent(JSON.parse(buf) as AgentEvent);
}
