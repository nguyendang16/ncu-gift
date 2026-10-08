import { useState } from "react";
import { Link } from "react-router-dom";
import { useAcceptSuggestions, useApplyReference, useCapability, useClassify, useConfirm, useMapColumns, useMeta, usePreview, useReference, useResolve, useReview, useSolicited, useUploadReference } from "../api/hooks";
import type { Capability, Option, ReviewItem } from "../api/types";
import { Chart } from "../components/Chart";
import { AiOffHint, DemoNotice, useAiReady } from "../components/AiParts";
import { AiBadge, Card, ErrorView, Icon, Notice, PageHeader, Pill, Q, Tabs } from "../components/ui";
import { useApp } from "../context/AppContext";
import { useI18n } from "../i18n";
import { C, axisText, baseOption, yMoney } from "../lib/chart";

type Tab = "upload" | "reference" | "capability" | "review" | "extras";

export function CapabilityList({ items }: { items: Capability[] }) {
  const { t } = useI18n();
  return (
    <div>
      {items.map((c) => (
        <div key={c.id} style={{ display: "grid", gridTemplateColumns: "110px 1fr", gap: 12, padding: "9px 0", borderTop: "1px solid var(--line-2)" }}>
          <div><Pill status={c.status} /></div>
          <div>
            <b>{c.label}</b>
            {c.reason && <div className="small" style={{ color: c.status === "blocked" ? "var(--red)" : "var(--amber)" }}>{c.reason}</div>}
            <div className="small muted">{t("cap.needs", { list: c.requires.join(t("ui.sep")) })}</div>
          </div>
        </div>
      ))}
    </div>
  );
}

function Upload() {
  const { setDatasetId } = useApp();
  const { t } = useI18n();
  const meta = useMeta(), preview = usePreview(), confirm = useConfirm();
  const aiMap = useMapColumns();
  const { status } = useAiReady();
  const [aiTags, setAiTags] = useState<Record<string, string>>({});
  const [map, setMap] = useState<Record<string, string>>({});
  const [name, setName] = useState("");
  const [ok, setOk] = useState(false);
  const p = preview.data;
  const onFile = (f?: File) => {
    if (!f) return;
    confirm.reset(); aiMap.reset(); setAiTags({});
    preview.mutate(f, { onSuccess: (r) => { setMap(Object.fromEntries(r.columns.map((c) => [c.name, c.proposed_field ?? ""]))); setName(f.name.replace(/\.\w+$/, "")); setOk(false); } });
  };
  const chosen = Object.values(map).filter(Boolean);
  const dup = chosen.filter((f, i) => chosen.indexOf(f) !== i);
  const need = (p ? p.columns.filter((c) => c.needs_confirmation).length : 0) + Object.keys(aiTags).length;
  const label = (k: string) => meta.data?.fields.find((f) => f.key === k)?.label ?? k;
  // AI only fills columns the rules left empty; every suggestion still needs the person's tick before import
  const askAi = () => p && aiMap.mutate(p.upload_id, { onSuccess: (r) => {
    const tags: Record<string, string> = {}, next = { ...map };
    const taken = new Set(Object.values(map).filter(Boolean));
    for (const s of r.suggestions) if (!next[s.column] && !taken.has(s.field)) { next[s.column] = s.field; tags[s.column] = s.reason; taken.add(s.field); }
    setMap(next); setAiTags(tags); setOk(false);
  } });
  const unmapped = p ? p.columns.filter((c) => !map[c.name]).length : 0;

  return (
    <>
      <Card icon="data" title={t("upload.step1")} sub={t("upload.step1_sub")}>
        <label className="drop" style={{ display: "block", cursor: "pointer" }}>
          <input type="file" accept=".xlsx,.xlsm,.csv" className="sr-only" onChange={(e) => onFile(e.target.files?.[0])} />
          <b>{preview.isPending ? t("upload.reading") : t("upload.choose")}</b>
          <div className="small muted">{t("upload.nothing_until")}</div>
        </label>
        <p className="small muted" style={{ marginTop: 10 }}>
          {t("upload.try")} <a href="/api/samples/mock_donations.xlsx" download>{t("upload.sample_a")}</a> {t("upload.or")} <a href="/api/samples/mock_donations_renamed.xlsx" download>{t("upload.sample_b")}</a> {t("upload.both_synthetic")}
        </p>
        {preview.isError && <ErrorView error={preview.error} />}
      </Card>
      {p && (
        <>
          <div style={{ height: 16 }} />
          <Card icon="check" title={t("upload.step2")} sub={t("upload.step2_sub", { file: p.filename, n: p.n_rows.toLocaleString(), sheets: p.sheets.join(", ") })}>
            <Notice tone="info">{p.row_note}</Notice>
            {unmapped > 0 && (
              <div style={{ display: "flex", gap: 12, alignItems: "center", flexWrap: "wrap", margin: "4px 0 10px" }}>
                <button className="btn ai" disabled={!status?.ready || aiMap.isPending} onClick={askAi}><Icon name="ai" size={17} />{aiMap.isPending ? t("ai.thinking") : t("upload.ai_button")}</button>
                <span className="small muted">{t("upload.ai_hint", { n: unmapped })}</span>
              </div>
            )}
            <AiOffHint /><DemoNotice />
            {aiMap.isError && <ErrorView error={aiMap.error} />}
            {aiMap.data && <Notice tone="ai" title={t("upload.ai_done_title")}>{aiMap.data.suggestions.length ? t("upload.ai_done", { n: Object.keys(aiTags).length }) : t("upload.ai_none")}</Notice>}
            <div className="scroll"><table className="t">
              <thead><tr><th>{t("upload.th_column")}</th><th>{t("upload.th_examples")}</th><th>{t("upload.th_means")}</th><th className="r">{t("upload.th_confidence")}</th></tr></thead>
              <tbody>{p.columns.map((c) => (
                <tr key={c.name} className={c.needs_confirmation ? "need" : ""}>
                  <td><b>{c.name}</b>{aiTags[c.name] !== undefined && <div className="small"><AiBadge /> <span className="muted">{aiTags[c.name]}</span></div>}{c.ambiguous && <div className="small" style={{ color: "var(--amber)" }}>{t("upload.ambiguous")}</div>}</td>
                  <td className="small muted">{c.sample.join(" · ")}</td>
                  <td>
                    <select className="inline" aria-label={t("upload.meaning_of", { column: c.name })} value={map[c.name] ?? ""} onChange={(e) => setMap({ ...map, [c.name]: e.target.value })}>
                      <option value="">{t("upload.extra_option")}</option>
                      {meta.data?.fields.map((f) => <option key={f.key} value={f.key}>{f.label}</option>)}
                    </select>
                    {c.needs_confirmation && c.alternatives.length > 0 && <div className="small muted">{t("upload.others", { list: c.alternatives.map((a) => label(a.field)).join(t("ui.sep")) })}</div>}
                  </td>
                  <td className="r num">{c.proposed_field ? `${Math.round(c.confidence * 100)}%` : aiTags[c.name] !== undefined ? t("upload.ai_unsure") : "–"}</td>
                </tr>
              ))}</tbody></table></div>
            {p.missing_fields.length > 0 && <Notice tone="warn" title={t("upload.not_found")}>{p.missing_fields.map(label).join(t("ui.sep"))}. {t("upload.not_found_tail")}</Notice>}
            {dup.length > 0 && <Notice tone="block">{t("upload.duplicate", { field: label(dup[0]) })}</Notice>}
            <div style={{ display: "flex", gap: 12, alignItems: "center", flexWrap: "wrap", marginTop: 8 }}>
              <label className="field">{t("upload.dataset_name")}<input type="text" value={name} onChange={(e) => setName(e.target.value)} /></label>
              {need > 0 && <label className="small"><input type="checkbox" checked={ok} onChange={(e) => setOk(e.target.checked)} /> {t("upload.checked", { n: need })}</label>}
              <button className="btn primary" disabled={dup.length > 0 || (need > 0 && !ok) || confirm.isPending}
                onClick={() => confirm.mutate({ upload_id: p.upload_id, name, mapping: Object.fromEntries(Object.entries(map).filter(([, v]) => v).map(([col, f]) => [f, col])) }, { onSuccess: (r) => setDatasetId(r.dataset_id) })}>
                {confirm.isPending ? t("upload.importing") : t("upload.import")}
              </button>
            </div>
            {confirm.isError && <ErrorView error={confirm.error} />}
          </Card>
        </>
      )}
      {confirm.data && (
        <>
          <div style={{ height: 16 }} />
          <Card icon="check" title={t("upload.step3")} sub={t("upload.step3_sub", { n: confirm.data.n_rows.toLocaleString(), review: confirm.data.review_items })}>
            <Notice tone="ok">{t("upload.imported_ok")} <Link to="/">{t("upload.open_overview")}</Link></Notice>
            <h3 style={{ marginBottom: 6 }}>{t("upload.supports")}</h3>
            <CapabilityList items={confirm.data.capability} />
          </Card>
        </>
      )}
    </>
  );
}

function Reference() {
  const { datasetId } = useApp();
  const { t, fmt } = useI18n();
  const q = useReference(), up = useUploadReference(), apply = useApplyReference();
  const s = q.data;
  return (
    <>
      <Card icon="data" title={t("ref.title")} sub={t("ref.sub")}>
        <label className="drop" style={{ display: "block", cursor: "pointer" }}>
          <input type="file" accept=".xlsx,.xlsm" className="sr-only" onChange={(e) => { const f = e.target.files?.[0]; if (f) up.mutate(f); e.target.value = ""; }} />
          <b>{up.isPending ? t("upload.reading") : t("ref.choose")}</b>
          <div className="small muted">{t("ref.hint")}</div>
        </label>
        {up.isError && <ErrorView error={up.error} />}
      </Card>
      <div style={{ height: 16 }} />
      <Card icon="check" title={t("ref.status_title")}>
        {!s?.loaded ? <Notice tone="info">{t("ref.none")}</Notice> : (
          <>
            <Notice tone="ok">{t("ref.loaded", { n: fmt.int(s.n_projects), file: s.filename ?? "" })}</Notice>
            {Object.keys(s.annual_by_year).length > 0 && (
              <p className="small muted">{t("ref.annual", { list: Object.entries(s.annual_by_year).map(([y, n]) => `${y}: ${n}`).join(" · ") })}</p>
            )}
            <div style={{ display: "flex", gap: 12, alignItems: "center", flexWrap: "wrap" }}>
              <button className="btn primary" disabled={apply.isPending} onClick={() => apply.mutate(datasetId)}>{apply.isPending ? t("upload.importing") : t("ref.apply")}</button>
              <span className="small muted">{t("ref.apply_hint")}</span>
            </div>
            {apply.isError && <ErrorView error={apply.error} />}
            {apply.data && <Notice tone="ok">{t("ref.applied", { rows: fmt.int(apply.data.rows_updated), review: apply.data.review_items })}</Notice>}
          </>
        )}
      </Card>
    </>
  );
}

function ReviewRow({ item, options, ai }: { item: ReviewItem; options: Option[]; ai?: { label: string; text: string; confidence: number } }) {
  const { t, fmt } = useI18n();
  const resolve = useResolve();
  const values = options.map((o) => o.value);
  const [label, setLabel] = useState(values.includes(item.proposed_label ?? "") ? item.proposed_label! : values[0]);
  const useAi = () => ai && values.includes(ai.label) && setLabel(ai.label);
  return (
    <tr>
      <td><span className="pill neutral">{item.kind === "purpose" ? t("review.kind_purpose") : t("review.kind_class")}</span></td>
      <td><b>“{item.raw_value}”</b>{ai && item.status === "pending" && (
        <div className="small"><AiBadge /> {t("review.ai_suggests", { label: ai.text, pct: fmt.pct(ai.confidence, 0) })} <button className="btn" style={{ minHeight: 28, padding: "2px 10px" }} onClick={useAi}>{t("review.ai_use")}</button></div>)}
        <div className="small muted">{t("review.records", { n: item.n_rows })}{item.proposed_text ? ` · ${t("review.suggestion", { label: item.proposed_text, pct: fmt.pct(item.confidence, 0) })}` : ` · ${t("review.no_suggestion")}`}</div></td>
      <td>{item.status === "resolved" ? <span className="pill ok">✓ {item.resolved_text}</span> : (
        <div style={{ display: "flex", gap: 8 }}>
          <select className="inline" aria-label={t("review.label_for", { value: item.raw_value })} value={label} onChange={(e) => setLabel(e.target.value)}>{options.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}</select>
          <button className="btn" disabled={resolve.isPending} onClick={() => resolve.mutate({ id: item.id, label })}>{t("review.apply")}</button>
        </div>)}
      </td>
    </tr>
  );
}

function Review() {
  const { datasetId } = useApp();
  const { t } = useI18n();
  const meta = useMeta();
  const q = useReview(datasetId);
  const classify = useClassify();
  const accept = useAcceptSuggestions();
  const { status } = useAiReady();
  const sug = new Map((classify.data?.suggestions ?? []).map((s) => [s.item_id, { label: s.label, text: s.label_text, confidence: s.confidence }]));
  return (
    <Q q={q}>{(items) => {
      const pending = items.filter((i) => i.status === "pending"), done = items.filter((i) => i.status === "resolved");
      const forAi = pending.filter((i) => i.kind === "purpose").map((i) => i.id);
      return (
        <Card icon="check" title={t("review.title")} sub={t("review.sub")}
          right={<span style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            {pending.some((i) => i.proposed_label) && <button className="btn primary" disabled={accept.isPending} onClick={() => accept.mutate(datasetId)}>{accept.isPending ? t("upload.importing") : t("review.accept_all")}</button>}
            {forAi.length > 0 && <button className="btn ai" disabled={!status?.ready || classify.isPending} onClick={() => classify.mutate({ dataset_id: datasetId, item_ids: forAi })}><Icon name="ai" size={17} />{classify.isPending ? t("ai.thinking") : t("review.ai_button")}</button>}</span>}>
          {accept.data && <Notice tone="ok">{t("review.accepted", { n: accept.data.accepted })}</Notice>}
          <AiOffHint /><DemoNotice />
          {classify.isError && <ErrorView error={classify.error} />}
          {pending.length === 0 && <Notice tone="ok">{t("review.empty")}</Notice>}
          <div className="scroll"><table className="t"><thead><tr><th>{t("review.th_kind")}</th><th>{t("review.th_value")}</th><th>{t("review.th_label")}</th></tr></thead>
            <tbody>
              {pending.map((i) => <ReviewRow key={i.id} item={i} ai={sug.get(i.id)} options={(i.kind === "purpose" ? meta.data?.purpose_labels : meta.data?.donor_classes) ?? []} />)}
              {done.map((i) => <ReviewRow key={i.id} item={i} options={[]} />)}
            </tbody></table></div>
        </Card>
      );
    }}</Q>
  );
}

function Extras() {
  const { datasetId, dataset } = useApp();
  const { t, fmt } = useI18n();
  const q = useSolicited(datasetId);
  return (
    <>
      <Card icon="data" title={t("extras.kept_title")} sub={t("extras.kept_sub")}>
        {dataset?.extra_columns.length ? dataset.extra_columns.map((c) => <span className="chip" key={c}>{c}</span>) : <p className="muted">{t("extras.none")}</p>}
      </Card>
      <div style={{ height: 16 }} />
      <Card icon="phone" title={t("extras.sol_title")} sub={t("extras.sol_sub")}>
        <Q q={q}>{(s) => {
          const b = baseOption();
          return (
            <>
              <Chart height={260} label={t("extras.sol_aria")} option={{
                ...b, tooltip: { ...b.tooltip, valueFormatter: (v: number) => fmt.ntd(v) },
                xAxis: { type: "category", data: s.tiers.map((x) => x.tier), axisLabel: axisText }, yAxis: yMoney(fmt.axisMoney),
                series: [
                  { name: t("extras.solicited"), type: "bar", stack: "s", data: s.tiers.map((x) => x.solicited_amount), itemStyle: { color: C.regular } },
                  { name: t("extras.unsolicited"), type: "bar", stack: "s", data: s.tiers.map((x) => x.unsolicited_amount), itemStyle: { color: C.grey } },
                ] }} />
              <table className="t"><thead><tr><th>{t("extras.th_size")}</th><th className="r">{t("extras.solicited")}</th><th className="r">{t("extras.unsolicited")}</th></tr></thead>
                <tbody>{s.tiers.map((x) => <tr key={x.tier}><td>{x.tier}</td><td className="r num">{fmt.ntd(x.solicited_amount)} ({x.solicited_count})</td><td className="r num">{fmt.ntd(x.unsolicited_amount)} ({x.unsolicited_count})</td></tr>)}</tbody></table>
              <div className="legend-note">{t("extras.column_used", { column: s.column })}</div>
            </>
          );
        }}</Q>
      </Card>
    </>
  );
}

export default function DataPage() {
  const { datasetId, dataset } = useApp();
  const { t } = useI18n();
  const [tab, setTab] = useState<Tab>("upload");
  const cap = useCapability(datasetId);
  return (
    <>
      <PageHeader title={t("data.title")} question={t("q.data")} desc={t("data.desc")} />
      <Tabs value={tab} onChange={setTab} tabs={[{ v: "upload", l: t("tab.upload") }, { v: "reference", l: t("tab.reference") }, { v: "capability", l: t("tab.capability") }, { v: "review", l: t("tab.review") }, { v: "extras", l: t("tab.extras") }]} />
      {tab === "upload" && <Upload />}
      {tab === "reference" && <Reference />}
      {tab === "capability" && <Card icon="shield" title={t("cap.title")} sub={dataset?.name}><Q q={cap}>{(c) => <CapabilityList items={c} />}</Q></Card>}
      {tab === "review" && <Review />}
      {tab === "extras" && <Extras />}
    </>
  );
}
