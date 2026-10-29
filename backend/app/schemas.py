"""Typed API contract. The frontend's TypeScript types are generated from these models
(see scripts/export_openapi.py), so a change here is a change to the contract."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class DatasetOut(BaseModel):
    id: int
    name: str
    is_mock: bool
    n_rows: int
    years: list[int]
    created_at: str
    mapped_fields: list[str]
    extra_columns: list[str]


class FieldInfo(BaseModel):
    key: str
    label: str


class Option(BaseModel):
    value: str
    label: str


class Meta(BaseModel):
    exceptional_threshold: float
    large_threshold: float
    risk_value_cap: float
    return_definitions: list[str]
    purpose_labels: list[Option]
    donor_classes: list[Option]
    fields: list[FieldInfo]


class Breakdown(BaseModel):
    label: str
    amount: float | None
    count: int
    share_amount: float | None
    share_count: float | None


class Kpis(BaseModel):
    total: float
    regular_total: float
    exceptional_total: float
    n_exceptional: int
    share_exceptional: float
    records: int
    in_kind_records: int
    donors: int
    large_gifts: int
    large_gifts_amount: float
    total_yoy_pct: float | None
    regular_yoy_pct: float | None
    retained_donors: int | None
    returning_donors: int | None
    repeat_selected: int | None
    prev_total: float | None = None
    prev_regular_total: float | None = None
    prev_repeat: int | None = None
    repeat_delta: int | None = None
    repeat_ratio: float | None = None
    card_gifts: int | None = None
    prev_card_gifts: int | None = None
    card_delta: int | None = None
    card_yoy_pct: float | None = None
    prev_large_gifts: int | None = None
    large_delta: int | None = None
    large_prior_avg: float | None = None
    million_amount: float = 0
    million_projects: int = 0
    million_share: float = 0
    top_project_share: float | None = None


class MonthRow(BaseModel):
    month: int
    total: float
    regular: float
    exceptional: float
    records: int


class ProjectTotal(BaseModel):
    project: str
    amount: float


class ClassYear(BaseModel):
    year: int
    amounts: list[float]


class ClassCompare(BaseModel):
    labels: list[str]
    series: list[ClassYear]


class KpiYear(BaseModel):
    year: int
    total: float
    regular_total: float
    exceptional_total: float
    n_exceptional: int
    donors: int
    records: int
    in_kind_records: int
    repeat: int | None = None
    large_gifts: int
    large_gifts_amount: float
    card_gifts: int | None = None
    card_amount: float | None = None


class OverviewOut(BaseModel):
    year: int
    prev_year: int | None
    years: list[int]
    scope: str
    scope_label: str
    kpis: Kpis
    kpi_compare: list[KpiYear]
    monthly: list[MonthRow]
    bands: list[Breakdown]
    donor_classes: list[Breakdown]
    class_compare: ClassCompare
    methods: list[Breakdown]
    purpose_groups: list[Breakdown]
    purpose_subs: list[Breakdown]
    colleges: list[Breakdown]
    projects_over_1m: list[ProjectTotal]
    notes: list[str]


class TrendRow(BaseModel):
    year: int
    total: float
    regular: float
    exceptional: float
    n_exceptional: int
    band_under: float = 0
    band_mid: float = 0
    band_over: float = 0
    donors: int
    records: int
    total_yoy_pct: float | None
    regular_yoy_pct: float | None


class JourneyYear(BaseModel):
    year: int
    history_available: bool
    active: int
    new: int | None
    retained: int | None
    reactivated: int | None
    lapsed: int | None


class CohortRate(BaseModel):
    n: int
    returned: int
    rate: float
    ci_low: float
    ci_high: float


class FunnelRow(BaseModel):
    cohort_year: int
    next_year: int
    first_time: CohortRate
    repeat: CohortRate


class JourneyOut(BaseModel):
    years: list[JourneyYear]
    funnel: list[FunnelRow]
    notes: list[str]


class PrecisionAtK(BaseModel):
    k: int
    hits: int
    precision: float
    value_captured: float
    random_expected: float
    lift_vs_random: float | None


class RiskMetrics(BaseModel):
    auc: float
    auc_ci_low: float
    auc_ci_high: float
    train: str
    test: str
    n_train: int
    n_test: int
    lapse_rate_train: float
    lapse_rate_test: float
    precision_at_k: list[PrecisionAtK]


class Coef(BaseModel):
    feature: str
    coef: float


class RiskDonor(BaseModel):
    donor_id: str
    donor_class: str | None
    donor_class_label: str
    p_lapse: float
    giving_last_year: float
    value_at_risk: float
    anonymous: bool
    tenure: int
    capped: bool
    reasons: list[str]


class RefStatus(BaseModel):
    loaded: bool
    filename: str | None = None
    uploaded_at: str | None = None
    n_projects: int = 0
    annual_by_year: dict[str, int] = {}


class ApplyRefIn(BaseModel):
    dataset_id: int | None = None


class ApplyRefOut(BaseModel):
    rows_updated: int
    review_items: int


class AcceptIn(BaseModel):
    dataset_id: int | None = None
    min_confidence: float = 0.5


class AcceptOut(BaseModel):
    accepted: int


class RiskPoint(BaseModel):
    donor_id: str
    donor_class: str | None
    donor_class_label: str
    giving_last_year: float
    p_lapse: float
    value_at_risk: float
    capped: bool


class RiskOut(BaseModel):
    scoring_year: int
    next_year: int
    metrics: RiskMetrics | None
    coefficients: list[Coef]
    donors: list[RiskDonor]
    points: list[RiskPoint]
    n_scored: int
    notes: list[str]


class Target(BaseModel):
    id: str
    kind: str
    label: str
    donors: int
    first_year: int | None = None


class Candidate(BaseModel):
    donor_id: str
    donor_class: str | None
    donor_class_label: str
    score: float
    evidence: list[str]
    last_gift_year: int
    total_given: float
    anonymous: bool
    components: dict[str, float]


class RankOut(BaseModel):
    target: str
    label: str
    as_of_year: int
    n_candidates: int
    candidates: list[Candidate]
    weights: dict[str, float]


class EvalK(BaseModel):
    k: int
    model: float
    model_ci_low: float
    model_ci_high: float
    lastyear: float
    lastyear_ci_low: float
    lastyear_ci_high: float
    popularity: float
    popularity_ci_low: float
    popularity_ci_high: float
    random: float
    random_ci_low: float
    random_ci_high: float


class EvalTarget(BaseModel):
    target: str
    positives: int
    model_p20: float | None
    lastyear_p20: float | None
    random_p20: float


class EvalOut(BaseModel):
    history_through: int
    holdout_year: int
    n_candidates: int
    n_targets: int
    by_k: list[EvalK]
    targets: list[EvalTarget]
    notes: list[str]


class ScenarioIn(BaseModel):
    dataset_id: int | None = None
    exceptional_threshold: float | None = None
    r1_uplift_pp: float = 0.0
    r2_uplift_pp: float = 0.0
    new_donor_multiplier: float = 1.0
    recurring_conversion_pct: float = 0.0
    major_gift_ntd: float = 0.0


class Band(BaseModel):
    expected: float
    low: float
    high: float


class ScenarioBand(Band):
    delta_vs_baseline: float


class ExceptionalLine(BaseModel):
    entered_gift: float
    total_if_gift_arrives: float
    note: str


class ObservedRate(BaseModel):
    k: int
    n: int
    rate: float
    ci_low: float
    ci_high: float


class Observed(BaseModel):
    first_time_retention: ObservedRate
    repeat_retention: ObservedRate
    recurring_retention: ObservedRate


class CohortRow(BaseModel):
    cohort: str
    donors: int
    retention_base: float | None
    retention_scenario: float | None
    avg_gift: float
    expected_base: float
    expected_scenario: float


class HistoryRow(BaseModel):
    year: int
    ordinary: float
    n_exceptional: int
    exceptional: float


class ScenarioOut(BaseModel):
    label: str
    base_year: int
    projection_year: int
    exceptional_threshold: float
    ordinary_last_year: float
    baseline: Band
    scenario: ScenarioBand
    exceptional_line: ExceptionalLine
    observed: Observed
    cohorts: list[CohortRow]
    history: list[HistoryRow]
    assumptions: list[str]


class Verification(BaseModel):
    verified: bool
    numbers_checked: int
    mismatches: list[str]


class BriefIn(BaseModel):
    dataset_id: int | None = None
    project: str
    exceptional_threshold: float | None = None
    use_ai: bool = False


class VerifyIn(BaseModel):
    text: str


class BriefOut(BaseModel):
    id: int
    title: str
    facts: dict[str, Any]
    draft_text: str
    verification: Verification
    source: str = "template"
    ai_note: str | None = None


class RollEntry(BaseModel):
    name: str
    amount: float
    recurring: bool


class RollProject(BaseModel):
    project: str
    entries: list[RollEntry]


class RollSection(BaseModel):
    heading: str
    projects: list[RollProject]


class InKindEntry(BaseModel):
    name: str
    item: str
    project: str


class RollStats(BaseModel):
    cash_entries: int
    masked_entries: int
    in_kind_entries: int
    friends_label: str


class RollOut(BaseModel):
    title: str
    year: int
    sections: list[RollSection]
    in_kind: list[InKindEntry]
    stats: RollStats


class LeakOut(BaseModel):
    anonymous_rows: int
    anonymous_rows_unmasked: int
    fully_anonymous_donors: int
    identity_occurrences_in_roll: int
    passed: bool


class Alt(BaseModel):
    field: str
    confidence: float


class ColumnProposal(BaseModel):
    name: str
    sample: list[str]
    proposed_field: str | None
    confidence: float
    ambiguous: bool
    needs_confirmation: bool
    alternatives: list[Alt]


class PreviewOut(BaseModel):
    upload_id: str
    filename: str
    sheets: list[str]
    n_rows: int
    columns: list[ColumnProposal]
    missing_fields: list[str]
    row_note: str


class Capability(BaseModel):
    id: str
    label: str
    status: str
    reason: str
    requires: list[str]
    missing: list[str]


class ConfirmIn(BaseModel):
    upload_id: str
    name: str
    mapping: dict[str, str]


class ConfirmOut(BaseModel):
    dataset_id: int
    n_rows: int
    review_items: int
    capability: list[Capability]


class ReviewOut(BaseModel):
    id: int
    kind: str
    raw_value: str
    proposed_label: str | None
    proposed_text: str | None
    confidence: float
    n_rows: int
    status: str
    resolved_label: str | None
    resolved_text: str | None


class ResolveIn(BaseModel):
    label: str


class SolicitedTier(BaseModel):
    tier: str
    solicited_amount: float
    solicited_count: int
    unsolicited_amount: float
    unsolicited_count: int


class SolicitedOut(BaseModel):
    column: str
    tiers: list[SolicitedTier]


class ConcentrationSummary(BaseModel):
    n_donors: int
    top1_donor_share: float
    top1pct_share: float
    top10pct_share: float
    gini: float


class CurvePoint(BaseModel):
    pct: float
    all: float
    ordinary: float


class ConcentrationOut(BaseModel):
    year: int
    all: ConcentrationSummary
    ordinary: ConcentrationSummary
    curve: list[CurvePoint]


class BridgeStep(BaseModel):
    key: str
    label: str
    value: float
    donors: int | None = None


class BridgeOut(BaseModel):
    year: int
    prev_year: int
    start: float
    end: float
    start_ordinary: float
    end_ordinary: float
    exceptional_start: float
    exceptional_end: float
    steps: list[BridgeStep]


class SeasonCell(BaseModel):
    year: int
    month: int
    value: float


class SeasonOut(BaseModel):
    years: list[int]
    cells: list[SeasonCell]


class TreeNode(BaseModel):
    name: str
    value: float
    children: list["TreeNode"] | None = None


class Highlight(BaseModel):
    id: str
    tone: str
    icon: str
    title: str
    text: str
    link: str


class AiStatus(BaseModel):
    configured: bool
    demo: bool
    model: str
    reasoning_effort: str | None
    enabled: bool
    share_project_names: bool
    share_column_headers: bool
    ready: bool
    daily_cap: int
    calls_today: int
    cost_today_usd: float


class AiSettingsIn(BaseModel):
    enabled: bool
    share_project_names: bool
    share_column_headers: bool


class AiTestOut(BaseModel):
    ok: bool
    model: str
    latency_ms: int
    reply: str
    demo: bool


class AiTurn(BaseModel):
    question: str
    answer: str


class NumberCheck(BaseModel):
    ok: bool
    checked: int
    unverified: list[str]


class AgentTable(BaseModel):
    columns: list[str]
    rows: list[list[str | int | float]]


class AgentLink(BaseModel):
    label: str
    to: str


class AgentStep(BaseModel):
    n: int
    tool: str
    title: str
    args_text: str = ""
    summary: str = ""
    table: AgentTable | None = None
    link: str | None = None
    links: list[AgentLink] = []
    visual: dict | None = None
    args_json: str = "{}"
    ok: bool


class AgentOut(BaseModel):
    answer: str
    verification: NumberCheck
    steps: list[AgentStep]
    model: str
    demo: bool
    cost_usd: float
    call_ids: list[int]
    repairs: int = 0
    llm_calls: int = 0
    conversation_id: int | None = None
    message_id: int | None = None


class AskIn(BaseModel):
    dataset_id: int | None = None
    question: str
    history: list[AiTurn] = []
    conversation_id: int | None = None
    year: int | None = None
    exceptional_threshold: float | None = None
    large_threshold: float | None = None


class AiMeta(BaseModel):
    model: str
    demo: bool
    cost_usd: float
    call_id: int


class AskOut(AiMeta):
    answer: str
    verification: NumberCheck
    sent: str


class InsightsIn(BaseModel):
    dataset_id: int | None = None
    year: int | None = None
    exceptional_threshold: float | None = None
    large_threshold: float | None = None


class Observation(BaseModel):
    key: str
    text: str


class Action(BaseModel):
    candidate_id: str
    title: str
    why: str
    now: str = ""
    steps: list[str]
    expected_effect: str
    measure: str = ""
    page: str
    link: AgentLink


class InsightsOut(AiMeta):
    observations: list[Observation]
    recommendations: list[str]
    actions: list[Action] = []
    verification: NumberCheck
    sent: str


class ChatMessage(BaseModel):
    id: int
    role: str
    text: str
    steps: list[AgentStep] = []
    verification: NumberCheck | None = None
    demo: bool = False
    feedback: int = 0
    created_at: str


class FeedbackIn(BaseModel):
    value: int


class FeedbackSummary(BaseModel):
    useful: int
    not_useful: int
    unrated: int


class ConversationRow(BaseModel):
    id: int
    title: str
    updated_at: str
    n_messages: int


class ConversationOut(BaseModel):
    id: int
    title: str
    messages: list[ChatMessage]


class MapIn(BaseModel):
    upload_id: str


class MapSuggestion(BaseModel):
    column: str
    field: str
    confidence: float
    reason: str


class MapOut(AiMeta):
    suggestions: list[MapSuggestion]


class ClassifyIn(BaseModel):
    dataset_id: int | None = None
    item_ids: list[int]


class ClassifySuggestion(BaseModel):
    item_id: int
    label: str
    label_text: str
    confidence: float


class ClassifyOut(AiMeta):
    suggestions: list[ClassifySuggestion]


class AiCallRow(BaseModel):
    id: int
    ts: str
    feature: str
    model: str
    status: str
    demo: bool
    duration_ms: int
    prompt_tokens: int
    completion_tokens: int
    cost_usd: float
    verified: bool | None
    error: str | None


class AiCallDetail(AiCallRow):
    payload_json: str
    response_excerpt: str
