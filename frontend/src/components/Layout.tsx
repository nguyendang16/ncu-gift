import { NavLink, Outlet } from "react-router-dom";
import { useAiStatus } from "../api/hooks";
import { useApp } from "../context/AppContext";
import { LANGS, useI18n } from "../i18n";
import type { Key } from "../i18n/en";
import { Icon, type IconName } from "./ui";

const NAV: { group: Key; items: { to: string; label: Key; icon: IconName; ai?: boolean }[] }[] = [
  { group: "nav.group.understand", items: [{ to: "/", label: "nav.overview", icon: "overview" }, { to: "/journey", label: "nav.journey", icon: "journey" }] },
  { group: "nav.group.ai", items: [{ to: "/ai", label: "nav.ai", icon: "ai", ai: true }] },
  { group: "nav.group.act", items: [
    { to: "/risk", label: "nav.risk", icon: "risk" }, { to: "/matching", label: "nav.matching", icon: "match" },
    { to: "/briefs", label: "nav.briefs", icon: "brief" }, { to: "/strategy", label: "nav.strategy", icon: "strategy" } ] },
  { group: "nav.group.output", items: [{ to: "/roll", label: "nav.roll", icon: "roll" }] },
  { group: "nav.group.data", items: [{ to: "/data", label: "nav.data", icon: "data" }] },
];

const EXC = [1e6, 5e6, 1e7, 5e7, 1e8];
const LARGE = [5e4, 1e5, 5e5];
const RETURN: Key[] = ["return.retained", "return.returning_after_gap", "return.either"];
const RETURN_VALUES = ["retained", "returning_after_gap", "either"];

export function LangSwitch() {
  const { lang, setLang, t } = useI18n();
  return (
    <div className="seg" role="group" aria-label={t("lang.label")}>
      {LANGS.map((l) => (
        <button key={l.value} aria-pressed={lang === l.value} onClick={() => setLang(l.value)} title={l.full} lang={l.value === "zh-TW" ? "zh-Hant" : "en"}>{l.label}</button>
      ))}
    </div>
  );
}

export default function Layout() {
  const { datasets, dataset, setDatasetId, settings, setSettings } = useApp();
  const { t, fmt } = useI18n();
  const ai = useAiStatus().data;
  const dot = ai?.ready ? (ai.demo ? "demo" : "on") : "";
  return (
    <div className="app">
      <aside className="side">
        <div className="brand">
          <div className="brand-mark">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#fff" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M4 11h16v10H4z M3 7h18v4H3z M12 7v14 M12 7c-2.5 0-4-1-4-2.5S9.5 2 12 7c2.5-5 4-2 4-2.5S14.5 7 12 7" /></svg>
          </div>
          <b>NCU GIFT<span>{t("brand.tagline")}</span></b>
        </div>
        <nav className="nav" aria-label={t("nav.aria")}>
          {NAV.map((g) => (
            <div key={g.group}>
              <div className="nav-group">{t(g.group)}</div>
              {g.items.map((i) => (
                <NavLink key={i.to} to={i.to} end={i.to === "/"} className={({ isActive }) => `${i.ai ? "ai " : ""}${isActive ? "active" : ""}`}>
                  <Icon name={i.icon} size={19} />{t(i.label)}
                  {i.ai && <span className={`dot ${dot}`} title={dot === "on" ? t("ai.st_on") : dot === "demo" ? t("ai.st_demo") : t("ai.st_off")} />}
                </NavLink>
              ))}
            </div>
          ))}
        </nav>
        <div className="settings" aria-label={t("settings.title")}>
          <div className="nav-group" style={{ padding: "0 0 2px" }}>{t("settings.title")}</div>
          <label>{t("settings.exceptional")}
            <select value={settings.exceptional} onChange={(e) => setSettings({ ...settings, exceptional: Number(e.target.value) })}>
              {EXC.map((v) => <option key={v} value={v}>{fmt.compact(v)}</option>)}
            </select>
          </label>
          <label>{t("settings.large")}
            <select value={settings.large} onChange={(e) => setSettings({ ...settings, large: Number(e.target.value) })}>
              {LARGE.map((v) => <option key={v} value={v}>{fmt.compact(v)}</option>)}
            </select>
          </label>
          <label>{t("settings.repeat")}
            <select value={settings.returnDef} onChange={(e) => setSettings({ ...settings, returnDef: e.target.value })}>
              {RETURN.map((k, i) => <option key={k} value={RETURN_VALUES[i]}>{t(k)}</option>)}
            </select>
          </label>
        </div>
      </aside>
      <div className="main">
        <header className="topbar">
          <label className="sr-only" htmlFor="ds">{t("topbar.dataset")}</label>
          <select id="ds" value={dataset?.id ?? ""} onChange={(e) => setDatasetId(Number(e.target.value))}>
            {datasets.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}
          </select>
          {dataset && <span className="muted small num">{t("topbar.records", { n: dataset.n_rows.toLocaleString(), years: dataset.years.join(", ") })}</span>}
          <span className="spacer" />
          {dataset?.is_mock && <span className="mock-tag" title={t("topbar.mock_title")}>● {t("topbar.mock")}</span>}
          <LangSwitch />
        </header>
        <main className="content"><Outlet /></main>
      </div>
    </div>
  );
}
