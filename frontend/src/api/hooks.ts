import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useLang } from "../i18n";
import { api } from "./client";
import type { ConversationOut, ConversationRow, AgentOut, AcceptOut, ApplyRefOut, RefStatus, AiCallDetail, AiCallRow, AiSettingsIn, AiStatus, AiTest, AiTurn, AskOut, Bridge, Brief, Capability, ClassifyOut, Concentration, Highlight, InsightsOut, MapOut, Season, TreeNode, ConfirmOut, Dataset, Journey, Leak, MatchEval, Meta, Overview, Preview, Rank, ReviewItem, Risk, Roll, Scenario, ScenarioIn, Solicited, Target, TrendRow } from "./types";

type ClassCompare = Overview["class_compare"];

// Every query key carries the language: the server translates the text it generates, so switching language refetches.
const on = (ds?: number) => ds !== undefined;

export function useMeta() {
  const lang = useLang();
  return useQuery({ queryKey: ["meta", lang], queryFn: () => api<Meta>("/api/meta"), staleTime: Infinity });
}
export function useDatasets() {
  const lang = useLang();
  return useQuery({ queryKey: ["datasets", lang], queryFn: () => api<Dataset[]>("/api/datasets") });
}
export function useTrend(ds: number | undefined, exceptional: number, bands?: { low: number; high: number }) {
  const lang = useLang();
  return useQuery({
    queryKey: ["trend", lang, ds, exceptional, bands], enabled: on(ds) && !!bands, placeholderData: keepPreviousData,
    queryFn: () => api<TrendRow[]>("/api/trend", { params: { dataset_id: ds, exceptional_threshold: exceptional, band_low: bands?.low, band_high: bands?.high } }),
  });
}
export function useClassCompare(ds: number | undefined, p: { scope: string; exceptional: number; min?: number; max?: number } | null) {
  const lang = useLang();
  return useQuery({
    queryKey: ["class-compare", lang, ds, p], enabled: on(ds) && !!p, placeholderData: keepPreviousData,
    queryFn: () => api<ClassCompare>("/api/class-compare", { params: { dataset_id: ds, scope: p?.scope, exceptional_threshold: p?.exceptional, amount_min: p?.min, amount_max: p?.max } }),
  });
}
export function useOverview(ds: number | undefined, p: { year?: number; compareYear?: number; scope: string; exceptional: number; large: number; returnDef: string }) {
  const lang = useLang();
  return useQuery({
    queryKey: ["overview", lang, ds, p], enabled: on(ds), placeholderData: keepPreviousData,
    queryFn: () => api<Overview>("/api/overview", { params: { dataset_id: ds, year: p.year, compare_year: p.compareYear, scope: p.scope, exceptional_threshold: p.exceptional, large_threshold: p.large, return_definition: p.returnDef } }),
  });
}
export function useJourney(ds?: number) {
  const lang = useLang();
  return useQuery({ queryKey: ["journey", lang, ds], enabled: on(ds), retry: false, queryFn: () => api<Journey>("/api/journey", { params: { dataset_id: ds } }) });
}
export function useRisk(ds?: number) {
  const lang = useLang();
  return useQuery({ queryKey: ["risk", lang, ds], enabled: on(ds), retry: false, queryFn: () => api<Risk>("/api/risk", { params: { dataset_id: ds, top_n: 50 } }) });
}
export function useTargets(ds?: number) {
  const lang = useLang();
  return useQuery({ queryKey: ["targets", lang, ds], enabled: on(ds), retry: false, queryFn: () => api<Target[]>("/api/matching/targets", { params: { dataset_id: ds } }) });
}
export function useRank(ds: number | undefined, target?: string) {
  const lang = useLang();
  return useQuery({ queryKey: ["rank", lang, ds, target], enabled: on(ds) && !!target, retry: false, queryFn: () => api<Rank>("/api/matching/rank", { params: { dataset_id: ds, target, n: 20 } }) });
}
export function useMatchEval(ds?: number) {
  const lang = useLang();
  return useQuery({ queryKey: ["matcheval", lang, ds], enabled: on(ds), retry: false, queryFn: () => api<MatchEval>("/api/matching/eval", { params: { dataset_id: ds } }) });
}
export function useScenario(body: ScenarioIn) {
  const lang = useLang();
  return useQuery({ queryKey: ["scenario", lang, body], enabled: on(body.dataset_id ?? undefined), retry: false, placeholderData: keepPreviousData, queryFn: () => api<Scenario>("/api/scenario", { body }) });
}
export function useRoll(ds: number | undefined, year?: number) {
  const lang = useLang();
  return useQuery({ queryKey: ["roll", lang, ds, year], enabled: on(ds), retry: false, queryFn: () => api<Roll>("/api/roll", { params: { dataset_id: ds, year } }) });
}
export function useLeak(ds?: number) {
  const lang = useLang();
  return useQuery({ queryKey: ["leak", lang, ds], enabled: on(ds), retry: false, queryFn: () => api<Leak>("/api/roll/leak-test", { params: { dataset_id: ds } }) });
}
export function useCapability(ds?: number) {
  const lang = useLang();
  return useQuery({ queryKey: ["capability", lang, ds], enabled: on(ds), queryFn: () => api<Capability[]>("/api/capability", { params: { dataset_id: ds } }) });
}
export function useReview(ds?: number) {
  const lang = useLang();
  return useQuery({ queryKey: ["review", lang, ds], enabled: on(ds), queryFn: () => api<ReviewItem[]>("/api/review", { params: { dataset_id: ds } }) });
}
export function useSolicited(ds?: number) {
  const lang = useLang();
  return useQuery({ queryKey: ["solicited", lang, ds], enabled: on(ds), retry: false, queryFn: () => api<Solicited>("/api/extras/solicited", { params: { dataset_id: ds } }) });
}

export const useCreateBrief = () => useMutation({ mutationFn: (b: { dataset_id?: number; project: string; exceptional_threshold: number; use_ai?: boolean }) => api<Brief>("/api/briefs", { body: b }) });
export const useVerifyBrief = () => useMutation({ mutationFn: (v: { id: number; text: string }) => api<Brief>(`/api/briefs/${v.id}/verify`, { body: { text: v.text } }) });

export function usePreview() {
  return useMutation({ mutationFn: (file: File) => { const f = new FormData(); f.append("file", file); return api<Preview>("/api/upload/preview", { form: f }); } });
}
export function useConfirm() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (b: { upload_id: string; name: string; mapping: Record<string, string> }) => api<ConfirmOut>("/api/upload/confirm", { body: b }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["datasets"] }),
  });
}
export function useResolve() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (v: { id: number; label: string }) => api<ReviewItem>(`/api/review/${v.id}/resolve`, { body: { label: v.label } }),
    // a resolved label changes classification, so every derived view must refresh
    onSuccess: () => qc.invalidateQueries(),
  });
}


// ---------------------------------------------------------------- richer charts
export function useConcentration(ds: number | undefined, year: number | undefined, exceptional: number) {
  const lang = useLang();
  return useQuery({ queryKey: ["concentration", lang, ds, year, exceptional], enabled: on(ds), retry: false, queryFn: () => api<Concentration>("/api/concentration", { params: { dataset_id: ds, year, exceptional_threshold: exceptional } }) });
}
export function useBridge(ds: number | undefined, year: number | undefined, exceptional: number, compareYear?: number) {
  const lang = useLang();
  return useQuery({ queryKey: ["bridge", lang, ds, year, compareYear, exceptional], enabled: on(ds), retry: false, queryFn: () => api<Bridge>("/api/bridge", { params: { dataset_id: ds, year, compare_year: compareYear, exceptional_threshold: exceptional } }) });
}
export function useSeasonality(ds: number | undefined, exceptional: number) {
  const lang = useLang();
  return useQuery({ queryKey: ["season", lang, ds, exceptional], enabled: on(ds), retry: false, queryFn: () => api<Season>("/api/seasonality", { params: { dataset_id: ds, exceptional_threshold: exceptional } }) });
}
export function usePurposeTree(ds: number | undefined, year: number | undefined, exceptional: number) {
  const lang = useLang();
  return useQuery({ queryKey: ["tree", lang, ds, year, exceptional], enabled: on(ds), retry: false, queryFn: () => api<TreeNode[]>("/api/purpose-tree", { params: { dataset_id: ds, year, exceptional_threshold: exceptional } }) });
}
export function useHighlights(ds: number | undefined, year: number | undefined, exceptional: number, compareYear?: number) {
  const lang = useLang();
  return useQuery({ queryKey: ["highlights", lang, ds, year, compareYear, exceptional], enabled: on(ds), retry: false, queryFn: () => api<Highlight[]>("/api/highlights", { params: { dataset_id: ds, year, compare_year: compareYear, exceptional_threshold: exceptional } }) });
}

// ---------------------------------------------------------------- AI
export function useAiStatus() {
  const lang = useLang();
  return useQuery({ queryKey: ["ai-status", lang], queryFn: () => api<AiStatus>("/api/ai/status"), staleTime: 5_000 });
}
const NEEDED = ["agent_links", "conversations", "plan_to_raise", "find_feature", "insight_actions"];
/** True when the running API is older than this page (it was started before an update and never restarted). */
export function useServerIsStale() {
  const q = useQuery({ queryKey: ["ai-version"], retry: false, staleTime: 60_000, queryFn: () => api<{ features: string[] }>("/api/ai/version") });
  if (q.isPending) return false;
  return q.isError || NEEDED.some((f) => !q.data?.features.includes(f));
}
export function useAiSettings() {
  const qc = useQueryClient();
  return useMutation({ mutationFn: (b: AiSettingsIn) => api<AiStatus>("/api/ai/settings", { method: "PUT", body: b }), onSuccess: () => qc.invalidateQueries({ queryKey: ["ai-status"] }) });
}
export function useAiTest() {
  const qc = useQueryClient();
  return useMutation({ mutationFn: () => api<AiTest>("/api/ai/test", { method: "POST", body: {} }), onSettled: () => { qc.invalidateQueries({ queryKey: ["ai-status"] }); qc.invalidateQueries({ queryKey: ["ai-log"] }); } });
}
export function useAsk() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (b: { dataset_id?: number; question: string; history: AiTurn[]; year?: number; exceptional_threshold: number; large_threshold: number }) => api<AskOut>("/api/ai/ask", { body: b }),
    onSettled: () => { qc.invalidateQueries({ queryKey: ["ai-status"] }); qc.invalidateQueries({ queryKey: ["ai-log"] }); },
  });
}
export function useAgent() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (b: { dataset_id?: number; question: string; conversation_id?: number; history: AiTurn[]; exceptional_threshold: number; large_threshold: number }) => api<AgentOut>("/api/ai/agent", { body: b }),
    onSettled: () => { qc.invalidateQueries({ queryKey: ["ai-status"] }); qc.invalidateQueries({ queryKey: ["ai-log"] }); qc.invalidateQueries({ queryKey: ["ai-conversations"] }); },
  });
}
export function useConversations() {
  return useQuery({ queryKey: ["ai-conversations"], queryFn: () => api<ConversationRow[]>("/api/ai/conversations", { params: { limit: 50 } }) });
}
export function useConversation(id?: number) {
  return useQuery({ queryKey: ["ai-conversation", id], enabled: id !== undefined, queryFn: () => api<ConversationOut>(`/api/ai/conversations/${id}`) });
}
/** One conversation, or all of them when no id is given. */
export function useDeleteConversation() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id?: number) => api<{ deleted: number }>(id === undefined ? "/api/ai/conversations" : `/api/ai/conversations/${id}`, { method: "DELETE" }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["ai-conversations"] }); },
  });
}
export function useInsights() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (b: { dataset_id?: number; year?: number; exceptional_threshold: number; large_threshold: number }) => api<InsightsOut>("/api/ai/insights", { body: b }),
    onSettled: () => { qc.invalidateQueries({ queryKey: ["ai-status"] }); qc.invalidateQueries({ queryKey: ["ai-log"] }); },
  });
}
export function useMapColumns() {
  return useMutation({ mutationFn: (upload_id: string) => api<MapOut>("/api/ai/map-columns", { body: { upload_id } }) });
}
export function useClassify() {
  return useMutation({ mutationFn: (b: { dataset_id?: number; item_ids: number[] }) => api<ClassifyOut>("/api/ai/classify", { body: b }) });
}
export function useAiLog() {
  const lang = useLang();
  return useQuery({ queryKey: ["ai-log", lang], queryFn: () => api<AiCallRow[]>("/api/ai/log", { params: { limit: 30 } }) });
}
export function useAiLogDetail(id?: number) {
  return useQuery({ queryKey: ["ai-log-detail", id], enabled: id !== undefined, queryFn: () => api<AiCallDetail>(`/api/ai/log/${id}`) });
}

export function useReference() {
  const lang = useLang();
  return useQuery({ queryKey: ["reference", lang], queryFn: () => api<RefStatus>("/api/reference") });
}
export function useUploadReference() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (file: File) => { const f = new FormData(); f.append("file", file); return api<RefStatus>("/api/reference", { form: f }); },
    onSuccess: () => qc.invalidateQueries({ queryKey: ["reference"] }),
  });
}
/** Re-reading the project table changes classifications, so every number built on them must be fetched again. */
const refreshAnalyses = (qc: ReturnType<typeof useQueryClient>) => qc.invalidateQueries();
export function useApplyReference() {
  const qc = useQueryClient();
  return useMutation({ mutationFn: (dataset_id?: number) => api<ApplyRefOut>("/api/reference/apply", { body: { dataset_id } }), onSuccess: () => refreshAnalyses(qc) });
}
export function useAcceptSuggestions() {
  const qc = useQueryClient();
  return useMutation({ mutationFn: (dataset_id?: number) => api<AcceptOut>("/api/review/accept-suggestions", { body: { dataset_id, min_confidence: 0.5 } }), onSuccess: () => refreshAnalyses(qc) });
}
