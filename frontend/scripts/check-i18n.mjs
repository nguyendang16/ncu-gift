// Run with: npm run check:i18n   (Node's built-in TypeScript stripping; no extra dependency)
// The compiler already guarantees zh-TW defines every key. This checks what types cannot:
// placeholder parity, and that no translation was left identical to English by accident.
import { en } from "../src/i18n/en.ts";
import { zhTW } from "../src/i18n/zh-TW.ts";

const ph = (s) => [...s.matchAll(/\{(\w+)\}/g)].map((m) => m[1]).sort().join(",");
const tags = (s) => (s.match(/<\/?b>/g) ?? []).join("");
const problems = [];
for (const [k, v] of Object.entries(en)) {
  if (k.endsWith("_one")) continue;
  const z = zhTW[k];
  if (z === undefined) { problems.push(`missing in zh-TW: ${k}`); continue; }
  if (ph(v) !== ph(z)) problems.push(`placeholders differ for ${k}: en {${ph(v)}} vs zh {${ph(z)}}`);
  if (tags(v) !== tags(z)) problems.push(`<b> tags differ for ${k}`);
  if (v === z && /[A-Za-z]{4,}/.test(v) && !/^(NT\$|AUC|EN$|OK$)/.test(v)) problems.push(`zh-TW identical to English (untranslated?): ${k} = "${v}"`);
}
for (const k of Object.keys(zhTW)) if (!(k in en)) problems.push(`zh-TW has unknown key: ${k}`);
if (problems.length) { console.error(problems.join("\n")); process.exit(1); }
console.log(`i18n ok: ${Object.keys(en).filter((k) => !k.endsWith("_one")).length} keys, en and zh-TW in step`);
