import { createContext, Fragment, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { en, type Key } from "./en";
import { zhTW } from "./zh-TW";

export type Lang = "en" | "zh-TW";
export const LANGS: { value: Lang; label: string; full: string }[] = [
  { value: "en", label: "EN", full: "English" },
  { value: "zh-TW", label: "繁中", full: "繁體中文" },
];
const CATALOGS: Record<Lang, Partial<Record<Key, string>>> = { en, "zh-TW": zhTW };
const STORE = "ncu.lang";

function detect(): Lang {
  try {
    const s = localStorage.getItem(STORE);
    if (s === "en" || s === "zh-TW") return s;
  } catch { /* storage unavailable */ }
  return typeof navigator !== "undefined" && navigator.language.toLowerCase().startsWith("zh") ? "zh-TW" : "en";
}

// The API client reads this on every request (Accept-Language); the provider keeps it in step with React state.
let current: Lang = detect();
export const getLang = () => current;

type Params = Record<string, string | number>;

export function translate(lang: Lang, key: Key, params?: Params): string {
  const cat = CATALOGS[lang];
  let msg: string | undefined;
  if (lang === "en" && params?.n === 1) msg = cat[`${key}_one` as Key];
  msg ??= cat[key] ?? en[key];
  return params ? msg.replace(/\{(\w+)\}/g, (_, k: string) => (k in params ? String(params[k]) : `{${k}}`)) : msg;
}

/** Renders <b>…</b> as bold; everything else is plain text, so translations never carry raw HTML. */
function bold(text: string): ReactNode {
  return text.split(/(<b>.*?<\/b>)/g).map((part, i) =>
    part.startsWith("<b>") ? <b key={i}>{part.slice(3, -4)}</b> : <Fragment key={i}>{part}</Fragment>);
}

export type Fmt = {
  ntd: (x: number | null | undefined) => string;
  compact: (x: number | null | undefined) => string;
  axisMoney: (v: number) => string;
  pct: (x: number | null | undefined, d?: number) => string;
  signedPct: (x: number | null | undefined) => string;
  int: (x: number | null | undefined) => string;
  month: (m: number) => string;
};

const trim = (n: number, d: number) => n.toFixed(d).replace(/\.?0+$/, "");

/** Taiwanese readers count in 萬 (10^4) and 億 (10^8), so compact amounts differ by language, not just in unit text. */
function makeFmt(lang: Lang): Fmt {
  const zh = lang === "zh-TW";
  const group = (n: number) => Math.round(n).toLocaleString("en-US");
  return {
    ntd: (x) => (x == null ? translate(lang, "ui.na") : `NT$${group(x)}`),
    compact: (x) => {
      if (x == null) return translate(lang, "ui.na");
      const a = Math.abs(x);
      if (zh) {
        if (a >= 1e8) return `NT$${trim(x / 1e8, 2)}億`;
        if (a >= 1e5) return `NT$${group(x / 1e4)}萬`;
        if (a >= 1e4) return `NT$${trim(x / 1e4, 1)}萬`;
        return `NT$${group(x)}`;
      }
      if (a >= 1e9) return `NT$${(x / 1e9).toFixed(2)}B`;
      if (a >= 1e6) return `NT$${(x / 1e6).toFixed(a >= 1e8 ? 0 : 1)}M`;
      if (a >= 1e3) return `NT$${(x / 1e3).toFixed(0)}k`;
      return `NT$${Math.round(x)}`;
    },
    axisMoney: (v) => {
      if (zh) return v >= 1e8 ? `${trim(v / 1e8, 2)}億` : v >= 1e4 ? `${trim(v / 1e4, 1)}萬` : `${v}`;
      return v >= 1e6 ? `${v / 1e6}M` : v >= 1e3 ? `${v / 1e3}k` : `${v}`;
    },
    pct: (x, d = 1) => (x == null ? "–" : `${(x * 100).toFixed(d)}%`),
    signedPct: (x) => (x == null ? "–" : `${x >= 0 ? "+" : ""}${x.toFixed(1)}%`),
    int: (x) => (x == null ? "–" : x.toLocaleString("en-US")),
    month: (m) => (zh ? `${m}月` : ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"][m - 1]),
  };
}

type Ctx = {
  lang: Lang;
  setLang: (l: Lang) => void;
  t: (key: Key, params?: Params) => string;
  tx: (key: Key, params?: Params) => ReactNode;
  fmt: Fmt;
};
const I18nCtx = createContext<Ctx>(null as unknown as Ctx);
export const useI18n = () => useContext(I18nCtx);
export const useLang = () => useContext(I18nCtx).lang;

export function I18nProvider({ children }: { children: ReactNode }) {
  const [lang, setLangState] = useState<Lang>(current);
  const setLang = useCallback((l: Lang) => {
    current = l;
    try { localStorage.setItem(STORE, l); } catch { /* storage unavailable */ }
    setLangState(l);
  }, []);
  useEffect(() => {
    current = lang;
    document.documentElement.lang = lang === "zh-TW" ? "zh-Hant-TW" : "en";
  }, [lang]);
  const value = useMemo<Ctx>(() => ({
    lang, setLang,
    t: (key, params) => translate(lang, key, params),
    tx: (key, params) => bold(translate(lang, key, params)),
    fmt: makeFmt(lang),
  }), [lang, setLang]);
  return <I18nCtx.Provider value={value}>{children}</I18nCtx.Provider>;
}
