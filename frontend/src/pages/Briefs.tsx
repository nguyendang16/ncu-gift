import { useEffect, useState } from "react";
import { useCreateBrief, useTargets, useVerifyBrief } from "../api/hooks";
import type { Brief } from "../api/types";
import { AiOffHint, DemoNotice, useAiReady } from "../components/AiParts";
import { AiBadge, Card, ErrorView, Icon, Notice, PageHeader } from "../components/ui";
import { useApp } from "../context/AppContext";
import { useI18n } from "../i18n";

type Facts = {
  project: string; category: string; year: number;
  category_last_year: { donors: number; gifts: number; median_gift: number; total_ordinary: number };
  options: { low: number; mid: number; high: number };
  top_channel: { name: string; pct: number }; top_class: { name: string; pct: number };
  alumni_share_top100_pct: number; lapsed_supporters: number;
};

export default function Briefs() {
  const { datasetId, settings } = useApp();
  const { t, tx, fmt } = useI18n();
  const targets = useTargets(datasetId);
  const projects = (targets.data ?? []).filter((x) => x.kind === "project");
  const [projectId, setProjectId] = useState<string>("");
  const create = useCreateBrief();
  const { ready } = useAiReady();
  const make = (use_ai: boolean) => create.mutate({ dataset_id: datasetId, project: projectName, exceptional_threshold: settings.exceptional, use_ai });
  const verify = useVerifyBrief();
  const [text, setText] = useState("");
  const brief: Brief | undefined = verify.data ?? create.data;
  useEffect(() => { if (create.data) setText(create.data.draft_text); }, [create.data]);
  useEffect(() => { if (!projectId && projects.length) setProjectId(projects[0].id); }, [projects, projectId]);
  const f = brief?.facts as Facts | undefined;
  const v = brief?.verification;
  // target ids look like "project:<canonical name>"; the API takes the canonical name
  const projectName = projectId.replace(/^project:/, "");

  return (
    <>
      <PageHeader title={t("briefs.title")} question={t("q.briefs")} desc={t("briefs.desc")}>
        <label className="field wide">{t("briefs.project")}
          <select value={projectId} onChange={(e) => setProjectId(e.target.value)}>{projects.map((p) => <option key={p.id} value={p.id}>{p.label}</option>)}</select>
        </label>
        <button className="btn primary" disabled={!projectId || create.isPending} onClick={() => make(false)}>
          {create.isPending && !create.variables?.use_ai ? t("briefs.building") : t("briefs.generate")}
        </button>
        <button className="btn ai" disabled={!projectId || create.isPending || !ready} onClick={() => make(true)} title={ready ? undefined : t("ai.hint_setup")}>
          <Icon name="ai" size={17} />{create.isPending && create.variables?.use_ai ? t("ai.thinking") : t("briefs.draft_ai")}
        </button>
      </PageHeader>
      {create.isError && <ErrorView error={create.error} />}
      <AiOffHint /><DemoNotice />
      {!brief && !create.isError && <Notice tone="info">{t("briefs.intro")}</Notice>}
      {brief && f && v && (
        <div className="grid g-main">
          <Card icon="brief" title={t("briefs.draft_title")} sub={t("briefs.draft_sub")}
            right={<span style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>{brief.source === "ai" ? <AiBadge /> : <span className="pill neutral">{t("briefs.src_template")}</span>}<span className={`pill ${v.verified ? "ok" : "blocked"}`}>{v.verified ? t("briefs.ok", { n: v.numbers_checked }) : t("briefs.bad", { n: v.mismatches.length })}</span></span>}>
            {brief.ai_note && <Notice tone="ai">{brief.ai_note}</Notice>}
            <textarea className="draft" value={text} onChange={(e) => setText(e.target.value)} aria-label={t("briefs.draft_aria")} />
            <div style={{ display: "flex", gap: 10, alignItems: "center", marginTop: 10, flexWrap: "wrap" }}>
              <button className="btn" disabled={verify.isPending} onClick={() => verify.mutate({ id: brief.id, text })}>{t("briefs.recheck")}</button>
              <button className="btn" disabled={!create.data} onClick={() => { const o = create.data!.draft_text; setText(o); verify.mutate({ id: brief.id, text: o }); }}>{t("briefs.reset")}</button>
              <span className="small muted">{t("briefs.llm_note")}</span>
            </div>
            {!v.verified && <Notice tone="block" title={t("briefs.blocked_title")}>{tx("briefs.blocked_text", { figures: v.mismatches.join(", ") })}</Notice>}
          </Card>
          <Card icon="data" title={t("briefs.facts_title")} sub={`${f.category} · ${f.year}`}>
            <table className="t"><tbody>
              <tr><td>{t("briefs.f_donors")}</td><td className="r num">{f.category_last_year.donors}</td></tr>
              <tr><td>{t("briefs.f_gifts")}</td><td className="r num">{f.category_last_year.gifts}</td></tr>
              <tr><td>{t("briefs.f_median")}</td><td className="r num">{fmt.ntd(f.category_last_year.median_gift)}</td></tr>
              <tr><td>{t("briefs.f_total")}</td><td className="r num">{fmt.compact(f.category_last_year.total_ordinary)}</td></tr>
              <tr><td>{t("briefs.f_options")}</td><td className="r num">{fmt.ntd(f.options.low)} · {fmt.ntd(f.options.mid)} · {fmt.ntd(f.options.high)}</td></tr>
              <tr><td>{t("briefs.f_channel")}</td><td className="r">{f.top_channel.name} ({f.top_channel.pct}%)</td></tr>
              <tr><td>{t("briefs.f_class")}</td><td className="r">{f.top_class.name} ({f.top_class.pct}%)</td></tr>
              <tr><td>{t("briefs.f_alumni")}</td><td className="r num">{f.alumni_share_top100_pct}%</td></tr>
              <tr><td>{t("briefs.f_lapsed")}</td><td className="r num">{f.lapsed_supporters}</td></tr>
            </tbody></table>
          </Card>
        </div>
      )}
    </>
  );
}
