import { useEffect, useRef, useState } from "react";
import { NavLink, Outlet, useLocation } from "react-router-dom";
import { useServerIsStale } from "../api/hooks";
import { useApp } from "../context/AppContext";
import { LANGS, useI18n } from "../i18n";
import type { Key } from "../i18n/en";
import { AiDock } from "./ai/Dock";
import { AiDockProvider, useAiDock } from "./ai/dockContext";
import { Icon, type IconName } from "./ui";

/** Five places, not nine pages: related pages become tabs inside their place. Routes are unchanged, so every link keeps working. */
type Tab = { to: string; label: Key };
const PLACES: { id: string; to: string; label: Key; icon: IconName; paths: string[]; tabs?: Tab[] }[] = [
  { id: "overview", to: "/", label: "nav.overview", icon: "overview", paths: ["/"] },
  { id: "donors", to: "/risk", label: "nav.donors", icon: "people", paths: ["/risk", "/matching", "/journey"],
    tabs: [{ to: "/risk", label: "sub.risk" }, { to: "/matching", label: "sub.matching" }, { to: "/journey", label: "sub.journey" }] },
  { id: "plan", to: "/strategy", label: "nav.plan", icon: "strategy", paths: ["/strategy", "/briefs"],
    tabs: [{ to: "/strategy", label: "sub.strategy" }, { to: "/briefs", label: "sub.briefs" }] },
  { id: "roll", to: "/roll", label: "nav.roll", icon: "roll", paths: ["/roll"] },
  { id: "data", to: "/data", label: "nav.data", icon: "data", paths: ["/data"] },
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

function SettingsMenu() {
  const { settings, setSettings } = useApp();
  const { t, fmt } = useI18n();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const close = (e: MouseEvent | KeyboardEvent) => { if (e instanceof KeyboardEvent ? e.key === "Escape" : !ref.current?.contains(e.target as Node)) setOpen(false); };
    document.addEventListener("mousedown", close); document.addEventListener("keydown", close);
    return () => { document.removeEventListener("mousedown", close); document.removeEventListener("keydown", close); };
  }, [open]);
  return (
    <div className="menu" ref={ref}>
      <button className="icon-btn" aria-expanded={open} aria-label={t("settings.title")} title={t("settings.title")} onClick={() => setOpen(!open)}><Icon name="sliders" size={18} /></button>
      {open && (
        <div className="menu-pop" role="dialog" aria-label={t("settings.title")}>
          <b>{t("settings.title")}</b>
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
      )}
    </div>
  );
}

function Shell() {
  const { datasets, dataset, setDatasetId } = useApp();
  const { open, wide } = useAiDock();
  const { t } = useI18n();
  const loc = useLocation();
  const stale = useServerIsStale();
  const place = PLACES.find((p) => p.paths.some((x) => (x === "/" ? loc.pathname === "/" : loc.pathname.startsWith(x))));
  return (
    <div className={`app ${open ? "dock-open" : ""} ${open && wide ? "dock-wide" : ""}`}>
      <aside className="side">
        <div className="brand">
          <div className="brand-mark">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#fff" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M4 11h16v10H4z M3 7h18v4H3z M12 7v14 M12 7c-2.5 0-4-1-4-2.5S9.5 2 12 7c2.5-5 4-2 4-2.5S14.5 7 12 7" /></svg>
          </div>
          <b>NCU GIFT</b>
        </div>
        <nav className="nav" aria-label={t("nav.aria")}>
          {PLACES.map((p) => (
            <NavLink key={p.id} to={p.to} end className={() => (place?.id === p.id ? "active" : "")}>
              <Icon name={p.icon} size={19} />{t(p.label)}
            </NavLink>
          ))}
        </nav>
      </aside>
      <div className="main">
        <header className="topbar">
          <label className="sr-only" htmlFor="ds">{t("topbar.dataset")}</label>
          <select id="ds" value={dataset?.id ?? ""} onChange={(e) => setDatasetId(Number(e.target.value))}>
            {datasets.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}
          </select>
          <span className="spacer" />
          {dataset?.is_mock && <span className="mock-tag" title={t("topbar.mock_title")}>● {t("topbar.mock")}</span>}
          <SettingsMenu />
          <LangSwitch />
        </header>
        <main className="content">
          {stale && (
            <div className="stale" role="alert">
              <b>{t("stale.title")}</b> {t("stale.text")} <code>make dev</code>
            </div>
          )}
          {place?.tabs && (
            <nav className="subtabs" aria-label={t(place.label)}>
              {place.tabs.map((x) => <NavLink key={x.to} to={x.to} className={({ isActive }) => (isActive ? "on" : "")}>{t(x.label)}</NavLink>)}
            </nav>
          )}
          <Outlet />
        </main>
      </div>
      <AiDock />
    </div>
  );
}

export default function Layout() {
  return <AiDockProvider><Shell /></AiDockProvider>;
}
