import { useState } from "react";
import { useLeak, useRoll } from "../api/hooks";
import { Card, Notice, PageHeader, Q } from "../components/ui";
import { useApp } from "../context/AppContext";
import { useI18n } from "../i18n";

export default function RollPage() {
  const { datasetId, dataset } = useApp();
  const { t, fmt } = useI18n();
  const [year, setYear] = useState<number | undefined>();
  const roll = useRoll(datasetId, year);
  const leak = useLeak(datasetId);
  const friends = roll.data?.stats.friends_label ?? "…";
  return (
    <>
      <PageHeader title={t("roll.title")} question={t("q.roll")} desc={t("roll.desc", { label: friends })}>
        <label className="field">{t("roll.year")}
          <select value={roll.data?.year ?? year ?? ""} onChange={(e) => setYear(Number(e.target.value))}>
            {(dataset?.years ?? []).map((y) => <option key={y}>{y}</option>)}
          </select>
        </label>
      </PageHeader>
      <Q q={leak}>{(l) => (
        <Notice tone={l.passed ? "ok" : "block"} title={l.passed ? t("roll.check_pass") : t("roll.check_fail")}>
          {t("roll.check_text", { unmasked: l.anonymous_rows_unmasked, rows: l.anonymous_rows, hits: l.identity_occurrences_in_roll, donors: l.fully_anonymous_donors })}
        </Notice>
      )}</Q>
      <Q q={roll}>{(r) => (
        <>
          <p className="muted small">{t("roll.summary", { cash: r.stats.cash_entries, masked: r.stats.masked_entries, label: r.stats.friends_label, inkind: r.stats.in_kind_entries })}{dataset?.is_mock && ` ${t("roll.mock_note")}`}</p>
          <div style={{ display: "grid", gap: 14 }}>
            {r.sections.map((s) => (
              <Card key={s.heading} title={s.heading}>
                <div className="cols">
                  {s.projects.map((p) => (
                    <div className="blk" key={p.project}>
                      <h3>{p.project}</h3>
                      {p.entries.map((e, i) => (
                        <div className="roll-entry" key={i}>
                          <span>{e.name}{e.recurring && <span className="muted small"> {t("roll.recurring")}</span>}</span>
                          <span className="amt">{fmt.ntd(e.amount)}</span>
                        </div>
                      ))}
                    </div>
                  ))}
                </div>
              </Card>
            ))}
            {r.in_kind.length > 0 && (
              <Card title={t("roll.inkind_title")} sub={t("roll.inkind_sub")}>
                <div className="cols">
                  {r.in_kind.map((k, i) => <div className="blk" key={i}><b>{k.name}</b><div className="small muted">{k.item}{k.project ? ` · ${k.project}` : ""}</div></div>)}
                </div>
              </Card>
            )}
          </div>
        </>
      )}</Q>
    </>
  );
}
