# NCU GIFT

React + FastAPI + SQLite. The repo ships with a **synthetic** dataset (every name, amount and donor in it is generated) so anyone can try the system. The real 2023–2025 ledger is **not** in the repo: you load it through the app (see *Running on the real ledger*), and it stays in your local database.

## Run it

```bash
make setup     # backend venv + pip install, frontend npm install
make dev       # API on :8000, web on :5173  (Ctrl-C stops both)
```

Open http://localhost:5173. The first start creates `data/ncu_gift.db` and loads the synthetic dataset through the same mapping and ingestion path an upload uses.

| Command | What it does |
|---|---|
| `make test` | 105 backend tests, frontend type-check, and the English/繁體中文 consistency check |
| `make types` | regenerate TypeScript types after editing `backend/app/schemas.py` |
| `make samples` | rewrite `sample_data/*.xlsx` |
| `make reset` | delete the database and uploads |

## Running on the real ledger

The real workbook has one sheet per year, Chinese headers, pseudonymised names in place of donor IDs, and other sheets (the finished donor roll, the requirements list). The staff also keep a project table. Load both through **Data & mapping**:

1. **Project table** tab → choose `募款專案紀錄、院系分類、提撥比例.xlsx`. The system reads the sheet `院系、提撥比例` (project name → category such as `院系教學研究-工-機` or `專案2026、2025`) and `專案紀錄` (each year's campaigns). This is what classifies gifts the way the staff do; rules are only the fallback.
2. **Upload & mapping** tab → choose `2023-2025 data + 需求.xlsx`. The sheets that are not donation records are skipped and named; the year sheets become the report year; with no donor-ID column, donors are identified by name (and the system says so wherever it matters).
3. **Review queue** → **Accept all suggestions** confirms every proposal the system made from the table's own patterns (for example a name starting with `學務處：` is sorted like the other 學務處 projects), and leaves the names it has no basis for to a person.

Check the result against the printed annual reports with `python backend/scripts/reconcile.py --api http://localhost:8000 --dataset <id> --out docs/reconciliation_INTERNAL.md` (the report figures are transcribed in the script). On the 2025 ledger the cash total (NT$258,348,643), the 819 cash records, all six gift-size band counts and all seven payment methods (amount and count) come out identical; the 2024 and 2023 totals agree to within 0.03%. Purpose categories, donor types and colleges depend on the staff's judgement and agree to within a few percent; the script lists every difference. The output is a working document for the team, not part of the submission.

## What is in it

| Page | What it shows | Backed by |
|---|---|---|
| Overview | headline sentence, rule-based "what to look at next" cards, stat cards with sparklines, combo chart (bars + donor line), waterfall "why did giving change", donut and treemap of where gifts go, month × year heatmap, concentration curve, detail tables folded away | `services/stats.py`, `services/insights.py` |
| Donor journey | Sankey of donors staying, stopping, joining and returning; flow bars; first-gift → second-gift funnel with 95% intervals | `services/journey.py` |
| At-risk donors | bubble chart (gift size × chance of stopping × money at stake); out-of-sample lapse model (trained 2023→24, tested 2024→25), ranked list with reasons | `services/risk.py` |
| Donor matching | best prospects for a category, department or project; each score is a stacked bar of the signals behind it, plus evidence; held-out evaluation against baselines | `services/matching.py` |
| Fundraising briefs | facts table + draft appeal, from a template or **Draft with AI**; every number in the draft is re-checked against the facts | `services/briefs.py`, `ai/features.py` |
| Goal planner | pick a goal ("raise NT$1M more"), see the ways to get there (keep more first-time donors, keep repeat donors, recruit, monthly giving, keep donors who might stop) and a recommended mix, press *Try this*, then fine-tune with plain-language sliders; the result states the range and progress toward the goal. Arithmetic on your own past rates, **not** a machine-learning model and not a forecast | `services/scenario.py`, `POST /api/plan` |
| Donor roll | recognition list; anonymous donors appear only as "Friends of NCU"; leak test | `services/roll.py` |
| Data & mapping | upload, column mapping with confirmation (optional **AI suggestions** for unmapped columns), capability matrix, review queue (optional **AI label suggestions**), extra columns | `ingest.py`, `services/capability.py` |
| AI assistant | ask-your-data chat, with setup steps while no key is configured | `backend/app/ai/`, `routers/ai.py` |

Try the flexible input: on *Data & mapping*, download `mock_donations_renamed.xlsx` (renamed and reordered columns, one Chinese header, payment method removed, extra columns) and upload it. It maps correctly, asks you to confirm the extra columns, switches off the payment-method analysis with the reason, and gives the same totals as the standard file.

## The AI analyst

The analyst is an AI that **cannot make up numbers**. The model is given tools that call the system's own analyses (overview, why the total changed, concentration, retention, who is likely to stop, best prospects for a target, what-if scenario, a goal planner, and a "where is it in the system" finder). It decides which to run; the system runs them; the model words the result.

- **Where it lives:** the **Ask AI** button at the bottom right of every page (or **Ctrl/⌘ + K**) opens a side panel that sits beside the page, like the assistants in Microsoft Copilot and Google Workspace; it can be widened, and the arrow opens the full-screen version at `/ai` (history on the left, conversation in the middle, like ChatGPT and Claude). Both share the same **saved history** (stored only in your local database; search, reopen, continue, delete one or all). The empty state offers four questions that fit the page you are on.
- **You watch it work.** Answers are streamed as they happen: each analysis appears as it finishes ("Plan to reach a goal ✓"), then "Writing the answer…" and "Checking every figure…".
- **Answers you can see, and touch.** The analysis behind an answer is drawn inside it (the waterfall for "why did the total change", the concentration curve, the monthly heat map, the donor flow, the trend). A what-if or a goal plan comes with **live sliders**: drag a lever and the range updates at once, with a progress bar toward the goal. No AI is involved when you drag; it is the same calculation as the Goal planner.
- **Rate every answer.** Thumbs up/down, copy and try again sit under each answer. Ratings are stored (`GET /api/ai/feedback-summary`): they are the evidence for "did this help staff?".
- **Questions it handles:** figures ("how many donors gave in 2025?"), who to call or ask, *what if* scenarios, **goals** ("I want to raise about NT$1M: what should we do?": which levers could do it, how many typical gifts that is, how much of the money at risk must be kept, a balanced plan, and three concrete next actions), and **where things are** ("where can I see who might stop giving?").
- **Buttons to the right page:** every answer ends with Go-to chips: one Open button to the page where you can see the same thing yourself, with the settings already applied (Goal planner sliders, the matching target, the Data tab).
- **Every figure has a source.** Each sentence cites the analysis it came from as a numbered circle, the card below shows which analysis and settings produced it, and every number in the answer is checked against the tool results.
- **Donor lists never pass through the model.** Tables of donors are drawn by the app; the tool results the model sees contain no donor name or code (the same safety gate as before checks each one).
- **Limits:** at most 6 model calls per question, only the allow-listed tools, arguments are validated and clamped, an invalid call becomes a message to the model rather than an error. Function calling on this model needs `reasoning_effort` "none", which the client sets.
- **Overview AI summary:** four observations and **four detailed next actions**. The model chooses and orders the actions and explains the situation; the steps, the expected effect (always an "if ..." with its assumption written next to it, never a forecast) and how to tell it worked come from the system's playbook and use figures computed from your data, so they are concrete and always checkable.
- **Measured quality:** `python backend/scripts/benchmark_agent.py --api http://localhost:8000 --dataset <id> --out docs/agent_benchmark.md` (see [docs/agent_benchmark.md](docs/agent_benchmark.md)). On the synthetic dataset, 52 questions in English and 繁體中文, the last three runs passed every question; read the caveats in that file before quoting it.

## AI features (OpenAI `gpt-6-luna`)

Opt-in, off by default, and never the source of a number.

| Where | What AI does | What it is allowed to see |
|---|---|---|
| Overview → AI summary | writes a short plain-language reading of the year | aggregate figures only |
| AI assistant → chat | answers questions about the data in English or Chinese | the same aggregate summary |
| Fundraising briefs → Draft with AI | words the brief from the computed facts table | the facts table for one project |
| Data → column meanings | suggests what unmapped upload columns mean | column headers and a statistical profile, never rows (needs the "column names" switch) |
| Data → review queue | suggests a purpose label for unclear project names | those names only (needs the "project names" switch) |

**Set it up once**

```bash
cp backend/.env.example backend/.env     # then put your key in OPENAI_API_KEY=
make dev                                 # restart so the key is picked up
```

Having a key in `backend/.env` is the consent: AI is on everywhere and may see project names and column headers (donor names and IDs are still blocked by the safety gate). The key is never sent to the browser. To go back to explicit per-feature switches, set `NCU_GIFT_AI_CONSENT=0`. To try every AI screen without a key, start the API with `NCU_GIFT_AI_DEMO=1`: replies are canned and labelled "demo".

**Safeguards, all enforced in code**

1. No key, no AI. With `NCU_GIFT_AI_CONSENT=0` the three permissions (AI on, project names, column names) are separate switches, all off until turned on (API: `PUT /api/ai/settings`).
2. Every payload passes a safety gate that rejects donor names and IDs before anything leaves the machine.
3. After the model answers, every number it quoted is matched against the facts it was given; one repair retry, then the answer is flagged "not found in the data".
4. Suggestions are limited to a closed set of known labels and capped in confidence, so they land in the review queue for a person.
5. Every call is recorded (payload, response excerpt, tokens, estimated cost) in the `ai_calls` table and readable at `GET /api/ai/log`; a daily cap (`NCU_GIFT_AI_DAILY_CAP`) stops runaway use.

**Tested how:** 26 tests against a fake transport, plus a hand run of every AI button against the real `gpt-6-luna` on the synthetic data (answers came back, numbers verified). Not yet tried on the real ledger. Prices in the cost estimate are configurable (`NCU_GIFT_LLM_PRICE_IN`, `_CACHED`, `_OUT`) because they are taken from the model page and may change.

## Languages: English and 繁體中文

The language switch (EN | 繁中) is in the top bar; the choice is remembered, and the first visit follows the browser language.

- **Interface text** lives in `frontend/src/i18n/en.ts` (source of truth) and `zh-TW.ts`. The compiler rejects a Chinese file that is missing a key, and `npm run check:i18n` also checks that placeholders and `<b>` tags match.
- **Text the API generates itself** (notes, reasons, evidence, capability messages, brief drafts, vocabulary labels) is translated on the server from `backend/app/locales/`, in the language of the request (`Accept-Language`). Numbers are never translated, and tests assert they are identical in both languages.
- **Amounts follow how each language counts:** `NT$41.6M` in English, `NT$4,160萬` and `NT$1.09億` in Chinese, including chart axes.
- **Vocabulary follows the Alumni Center's own documents** (中大之友, 指定用途, 回流續捐, 芳名錄, the band wording `1萬(含)以下`…). Anonymous donors appear as `中大之友`, the same convention as the staff's donor-roll sample.
- **Values that come from the data are shown as entered**, in whatever language they were typed (a raw project name in an upload, a free-text "Gift for students"). There is no machine translation anywhere; it was considered and left out on purpose.
- **The Chinese is a first draft and needs a native reader.** Department, college and project names for the synthetic catalogue (`zh_TW.py`, sections `_DEPT`, `_COLLEGE`, `_PROJECT`) are best guesses at official names, and the statistical wording (信賴區間, 樣本外, 敏感度分析) should be checked by someone who writes it daily.

**Add a language:** add `backend/app/locales/<code>.py` and register it in `i18n.py` (`SUPPORTED`, `CATALOGS`); add `frontend/src/i18n/<code>.ts` and register it in `i18n/index.tsx` (`LANGS`, `CATALOGS`, and the number formats in `makeFmt`). The tests and the type-check tell you what is missing.

## Rules the code enforces

1. **Numbers are computed, never generated.** All figures come from explicit code; the draft text only wraps them, and a verifier blocks any number not in the facts table.
2. **Missing is not zero.** Missing amounts stay null (in-kind gifts show N/A); an analysis without its required columns says what is missing and why.
3. **Everything adjustable is a parameter:** exceptional-gift threshold, large-gift threshold, repeat-donor definition, risk value cap.
4. **Low confidence goes to a person.** Purpose and donor-type guesses below 0.8 wait in the review queue; one answer updates every matching record.
5. **Anonymity is enforced in code.** One function is the only way a name reaches the roll; names live in their own table, apart from the analytics frame.
6. **Total revenue is not forecast.** Only ordinary giving is modelled; any exceptional gift is a separate, user-entered line.
7. **AI words things; it does not decide or calculate.** See *AI features* above.

## Layout

```
backend/app/    main.py · ingest.py (WP1) · org.py (WP2) · services/ (WP3–6, 8) · routers/ · schemas.py · models.py
backend/tests/  39 tests: the safety rules above, plus bilingual parity and per-endpoint checks in both languages
frontend/src/i18n/  en.ts · zh-TW.ts · index.tsx (provider, t(), number formats) · scripts/check-i18n.mjs
frontend/src/   pages/ · components/ · api/ (generated types + hooks) · lib/
sample_data/    two synthetic workbooks for the upload flow
```

## Status against the work packages

| WP | State |
|---|---|
| WP1 ingestion and column mapping | Rule-based first (headers + content); optional AI suggestions for columns the rules leave unmapped, always confirmed by a person. **AI part untested against the real API** |
| WP2 classification | The staff's own project table first (exact names, the year's campaign list), then proposals learned from its patterns, then rules; everything below 0.8 confidence waits in the review queue, which can accept all proposals at once. Optional AI label suggestions (closed label set, capped confidence) |
| WP3 statistics engine | Working and parametrised, and reconciled against the 2023–2025 annual reports (see *Running on the real ledger*). **Not yet compared with the staff's budget deck** |
| WP4 lapse risk | Working with a real temporal holdout. On the real ledger: AUC 0.71 (95% interval 0.67–0.75), trained 2023→24 and tested on 2024→25 |
| WP5 matching | Working with the held-out evaluation. On the real ledger the ranking beats "gave to it last year" and "most active donors" at 20 contacts, with wide intervals because only a few new projects can be tested |
| WP6 strategy and briefs | Explorer and verified briefs working; the draft is a template or AI-worded, both number-checked. **No staff usefulness rating yet** |
| WP7 frontend | All pages above, in English and 繁體中文. Redesigned (hero, cards, 11 chart types). Checked by hand on desktop in both languages, with a scan for untranslated text, and on a phone-width window for Overview, AI assistant, Risk, Journey and Strategy; **no frontend or end-to-end tests** |
| WP8 donor roll | Working with the anonymity rule and leak test. **Downloads (charts, tables, summaries) are not built** |
| WP12 API and storage | Working. No authentication, single user, local only |

Also not done: downloads of charts and tables (PNG/CSV), a real-ledger run (needs Chinese project-name rules), recurring-gift charge-level resolution (needs data the staff have not supplied), receipt dates, the solicited flag beyond the demo view, and the annual-report layout (out of scope).

## Known rough edges

- Pages load as separate chunks, but the ECharts chunk is still ~690 kB (233 kB gzipped); it loads once, on the first page that draws a chart.
- Uploaded files stay on disk under `data/uploads/`; there is no clean-up.
- `echarts-for-react` is CommonJS, so `components/Chart.tsx` resolves its default export defensively; keep that if you upgrade.
- Chart animation is switched off on purpose (`lib/chart.ts`): the grow-in stalls in background tabs and in screenshots.
