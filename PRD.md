# MyMarket MCP: Product Requirements Document

Version 0.1. Date: 2026-10-10. Status: hackathon MVP. Backend only.

Implementation ownership update: this repository owns the MCP app, inference,
and handoff validation. The teammate owns historical preprocessing and training
in Google Colab. `DATA_AGENT_PROMPT.md` is the canonical versioned interface.
No local training script or teammate-owned notebook is maintained here. All app
tools are implemented; real readiness still requires the teammate's exports.

One line: an MCP server that reads live Malaysian news, finds stories tied to tracked products, predicts if the story points to price UP, DOWN or STABLE, checks that call against official price data, and explains it in plain words.

---

## 0. Read first: flags

You asked me to flag anything that does not make sense. These are the issues. Each has a fix already built into this plan.

**F1. "Positive / negative impact" is vague.**
Positive for whom? Shoppers or sellers? Fix: output price direction only. UP, DOWN, STABLE. Add a plain tag "bad for shoppers" (UP) or "good for shoppers" (DOWN).

**F2. Price data covers only some goods.**
PriceCatcher is a grocery and daily-needs price survey. There is no data for electronics, rent, cars and so on. Your domains are Staple Food (rice, egg, cooking oil, chicken) and Consumer Products. Consumer Products items are NOT chosen yet. Fix: the data agent first writes `item_catalog_report.md` from `lookup_item`. You pick 3 to 5 consumer items that really exist in PriceCatcher. Fuel is dropped (not in your domains).

**F3. News years and price years do not fully overlap.**
News is 2020 to 2026. I could NOT confirm the first month of PriceCatcher files on data.gov.my. Latest verified file is 2026-09, updated 1 Oct 2026. Fix: the download script probes each month and skips 404. Training uses only the overlap. Older news is only used to test the relevance filter.

**F4. News rarely moves grocery prices within two weeks.**
Signal is weak. Accuracy will be modest. Fix: compare against honest baselines (majority class, price momentum, keyword rules). Report macro-F1 with confidence intervals. Let the model abstain when confidence is low. Position the product as an awareness alert, not a forecast. Do not oversell in the pitch.

**F5. Fuel prices are government set.**
Weekly price comes from the Automatic Pricing Mechanism. News predicts policy, not market moves. There are structural breaks: diesel subsidy removal on 10 Jun 2024 (RM2.15 to RM3.35 in Peninsular Malaysia), and RON95 changes on 30 Sep 2025 (RM2.60 market, RM1.99 BUDI95, RM2.05 SKPS). Fix: fuel is stretch only. Mark break weeks. Exclude them from training or add a flag.

**F6. Random train/test split will cheat.**
One event produces many articles with the same label. Fix: split by time. Add a 14 day purge gap. Add rolling-origin backtest by quarter.

**F7. Heavy class imbalance.**
Most articles are irrelevant. Most price windows are STABLE. Fix: class weights, per-product thresholds, macro-F1 as main metric. Never report plain accuracy alone.

**F8. Source mismatch.**
Kaggle sample URLs point to thestar.com.my, so training data looks like The Star only. Live RSS from other outlets has different style. Fix: use The Star feed if one exists (I could not verify its URL, check thestar.com.my/rss). Treat other outlets as an out-of-source test.

**F9. Scrapling caution.**
Scrapling is fine for article body text. Its stealth fetchers are built to bypass anti-bot systems. Do not use them on sites that block bots. Use plain `Fetcher`, obey robots.txt, 1 request per second, cache everything. Sample data shows `content_tier = Complimentary`, so some articles are premium. Fix: if body is paywalled, fall back to RSS summary.

**F10. PriceCatcher has no API.**
Data.gov.my says it is not available through OpenAPI. It is monthly CSV/Parquet files with over a million rows per month. Fix: preprocess offline into a small daily table. MCP never reads raw files. The data.gov.my API (4 requests per minute limit) is used for fuel only.

**F11. Price index is noisy.**
Premises change from day to day, so a raw median can jump. Fix: robust median, outlier trim, 7 day smoothing. Upgrade later to matched-premise price changes.

**F12. LLM summary can invent numbers.**
Fix: LLM only receives model output and computed facts. Strict JSON schema. Rule: no new figures.

**F13. Not financial advice.**
Every alert carries a short awareness-only disclaimer.

### Things I could not verify
- Kaggle dataset row count, exact date range, update day.
- First month of PriceCatcher files.
- The Star RSS feed URL.
- Current free-tier limits of any LLM provider. Check on the day.

---

## 1. Goal and non-goals

**Goals**
1. Pull Malaysian news live from free sources.
2. Keep only articles tied to tracked domains and products.
3. Predict price direction per product with a trained model.
4. Validate predictions against Malaysian price data. Report honest accuracy.
5. Explain impact on domain and products in simple sentences.
6. Expose all of it as MCP tools.

**Non-goals**
- No UI. Claude Desktop or MCP Inspector is the client.
- No price level forecast. Direction only.
- No trading signals.
- No paid APIs.

---

## 2. Users and use cases

| User | Question | Tool |
|---|---|---|
| Consumer | "Will chicken get pricier soon?" | `scan_alerts` |
| Journalist | "Which news this week hints at price pressure?" | `scan_alerts` |
| Policy analyst | "How accurate is this model?" | `backtest_report`, `forward_validation` |
| Judge | "Show me one full example." | `predict_impact` + `price_context` |

---

## 3. Architecture

```
 RSS feeds ──> feed reader ──> Scrapling Fetcher (article body) ──> SQLite cache
                                                                      │
                                                    relevance filter (aliases + embeddings)
                                                                      │
                          price index (daily, from PriceCatcher) ──┐  ▼
                                                                   ├─> impact model ──> predictions table
                          fuel price (weekly, data.gov.my API) ────┘            │
                                                                                ▼
                                                     LLM explainer (JSON, grounded)
                                                                                │
                                                                  MCP server (FastMCP)
                                                                                │
                                                       Claude Desktop / MCP Inspector

 Offline (run once, on laptop + Colab):
 Kaggle news ─┐
              ├─> build labels (event study) ─> train model ─> models/*.joblib
 PriceCatcher ┘
```

---

## 4. Data sources

| Source | What | Access | Notes |
|---|---|---|---|
| Kaggle "News Article (Weekly Updated)" `azraimohamad/news-article-weekly-updated` | Training news | Kaggle login, CLI or manual download | Columns: content_id, title, text, section, category, content_tier, content_length, authors, published_date, keywords, summary, url |
| PriceCatcher (KPDN via data.gov.my) | Daily item prices per premise | `https://storage.data.gov.my/pricecatcher/pricecatcher_YYYY-MM.parquet` | Columns: date, premise_code, item_code, price. License CC BY 4.0. Updated daily 12:00 |
| PriceCatcher item lookup | item_code to name | `.../pricecatcher/lookup_item.parquet` | Columns: item_code, item, unit, item_group, item_category |
| PriceCatcher premise lookup | premise_code to place | `.../pricecatcher/lookup_premise.parquet` | Columns: premise_code, premise, address, premise_type, state, district |
| Fuel price | Weekly RON95, RON97, diesel | `https://storage.data.gov.my/commodities/fuelprice.parquet` or `https://api.data.gov.my/data-catalogue?id=fuelprice` | Columns: series_type (level, change_weekly), date, ron95, ron97, diesel, diesel_eastmsia, ron95_budi95, ron95_skps. Next update weekly |
| Live news RSS | Fresh articles | Free | Checked on 2026-10-10. Malay Mail `https://www.malaymail.com/feed/rss/malaysia`: WORKS, 18 items, newest 10 Oct 2026, has title, link, description, content:encoded, pubDate. Bernama `https://www.bernama.com/en/rssfeed.php`: WORKS, 10 items, but no pubDate (get date from article page or use fetch time). FMT `https://www.freemalaysiatoday.com/feed/`: NOT confirmed, my fetch failed. Test in browser. The Star: NOT found. Its `/rss` page showed no feed URLs. Open `thestar.com.my/rss` in a browser, right click each RSS icon, copy link |
| Scrapling | Article body | `pip install "scrapling[fetchers]"`, Python 3.10+ | Use `Fetcher` only. `page.markdown()` gives clean text |
| LLM explainer | Plain-language summary | Gemini free tier via Google AI Studio, or Groq free tier, or Ollama local | Check current model names and limits |

Rule: PriceCatcher says its data is for price surveillance. For inflation analysis, DOSM CPI is the right source. Say this in the demo.

---

## 5. Domains and products (MVP)

Two domains. Updated 2026-10-10.

**Domain 1: Staple Food** (PriceCatcher). Four products.

| Product | EN aliases | BM aliases |
|---|---|---|
| rice | rice | beras, nasi (careful), padi |
| egg | egg, eggs | telur |
| cooking_oil | cooking oil, vegetable oil, palm cooking oil | minyak masak |
| chicken | chicken, poultry, broiler | ayam |

**Domain 2: Consumer Products** (PriceCatcher, if items exist). Products NOT chosen yet.
1. Data agent runs `scripts/00_item_catalog.py`. It writes `item_catalog_report.md` with every `item_group`, `item_category`, item count, and example item names.
2. You pick 3 to 5 consumer items that appear in that report with good coverage (many premises, many days).
3. Fill them into `config/products.yaml`. Until then, build everything for Staple Food only.
4. If PriceCatcher has no good consumer items, tell the team. Options: keep one domain, or use DOSM CPI sub-indices (monthly, thinner for labels).

Fuel is dropped. It is not in your domains.

Each product maps to `item_code` values by searching `lookup_item`. Agent proposes, human reviews (M3).

Event words used as features (EN and BM): subsidy, subsidi, ceiling price, harga siling, shortage, kekurangan, flood, banjir, import ban, export ban, tariff, levy, SST, price control, kawalan harga, festive, Hari Raya, Ramadan, Chinese New Year, ringgit, floods, drought, bird flu, feed cost, minimum wage.

Config lives in `config/products.yaml`:

```yaml
domains:
  staple_food:
    products:
      chicken:
        aliases_en: [chicken, poultry, broiler]
        aliases_ms: [ayam]
        item_codes: []      # filled by script 03, reviewed by human
        exclude_phrases: [chicken rice shop, ayam brand]   # noise
```

---

## 6. Functional requirements

### 6.1 News ingestion (live)
- Read all configured RSS feeds. Use `feedparser`.
- Dedupe by URL, then by near-duplicate title (cosine > 0.9 within 3 days).
- For each new URL, fetch body with Scrapling `Fetcher`. Convert to text.
- Rate limit 1 request per second per host. Cache in SQLite. Respect robots.txt.
- If fetch fails or looks paywalled (text under 300 chars), use RSS summary.
- Store: id, title, source, published_at (Asia/Kuala_Lumpur), url, summary, body, language.

### 6.2 Relevance filter
Two stages.
1. Alias match on title + summary + first 1500 chars of body. Case-insensitive. Word boundary. Apply exclude phrases.
2. Embedding check with `intfloat/multilingual-e5-small`. Compare article to product description sentences. Drop if cosine under tuned threshold. Threshold is tuned on the manual audit set (M5).

Output: list of (article, product, match_score, matched_terms).

### 6.3 Impact model
- Input: text = `title. summary. first 1500 chars of body`, product, domain, event-word flags.
- Output: probabilities for UP, DOWN, STABLE. Calibrated.
- Abstain if max probability under `min_confidence` (default 0.55).
- Versions:
  - v0 baseline: TF-IDF + logistic regression. Minutes on CPU.
  - v1 main: multilingual-e5-small embeddings + product one-hot + event flags into LogisticRegression or LightGBM. Calibrate with isotonic or Platt on validation set.
  - v2 optional: fine-tune `distilbert-base-multilingual-cased` on Colab T4. Ship only if macro-F1 beats v1 on the test set.

### 6.4 Label construction (offline)
Price index for product p:
1. Per item_code, daily median price across premises. Drop price <= 0. Drop prices over 3x or under 1/3 of item's rolling 30 day median.
2. Normalize each item by its own median over its first 90 days.
3. `I_p(t)` = mean over items in product p. Then 7 day rolling mean.

Label for example (article a, product p, publish date d):
```
base = I_p(d - 1)
fut  = I_p(d + H)          # H = 14 days default, config
ret  = fut / base - 1
theta_p = k * std(ret over TRAIN period only)    # k = 0.5 default
UP     if ret >  theta_p
DOWN   if ret < -theta_p
STABLE otherwise
```
Skip example if index missing in window or too few premises reported that day. Store `ret` too for analysis.

### 6.5 Validation (this is the "check against price data" step)
Offline:
- Time split: train oldest 70%, val next 15%, test newest 15%. Purge 14 days between.
- Rolling-origin: train on all before quarter Q, test on Q. Repeat.
- Metrics: macro-F1, per-class precision and recall, confusion matrix, directional accuracy on non-STABLE only, bootstrap 95% CI on macro-F1.
- Baselines: majority class, momentum (sign of previous 14 day return), keyword rules.
- Alert precision: of alerts with p >= 0.7, share where realized direction matched.

Online (forward validation):
- Every prediction is logged with timestamp and horizon.
- After H days, a job reads fresh PriceCatcher data, computes realized label, stores outcome.
- `forward_validation` reports running accuracy.

### 6.6 AI explainer
- Input: article title, source, date, product, direction, probabilities, top trigger terms, `price_context` numbers.
- Output JSON:
```json
{
  "headline": "string, max 12 words",
  "domain_impact": "1 to 2 plain sentences",
  "product_impacts": [{"product": "chicken", "direction": "UP", "why": "1 sentence"}],
  "confidence_note": "1 sentence on uncertainty",
  "disclaimer": "awareness only, not financial advice"
}
```
- Hard rules in prompt: use only given facts, no new numbers, no names not in the article, simple words, optional `lang=ms`.
- Validate JSON with pydantic. Retry once. Fall back to a template sentence if LLM fails.

---

## 7. MCP tool spec

Server name: `mymarket`. Python `mcp` SDK (FastMCP). Transport: stdio (default), streamable HTTP optional.

| Tool | Inputs | Returns |
|---|---|---|
| `list_domains` | none | domains, products, aliases |
| `fetch_news` | hours=48, sources=None, limit=100 | articles: id, title, source, published_at, url, summary |
| `filter_relevant` | domain=None, hours=48 | articles with matched products, score, terms |
| `predict_impact` | url or text, products=None | per product: direction, probs, confidence, triggers, abstained |
| `price_context` | product, days=90 | latest index, change 7d, 30d, series tail, data_as_of |
| `scan_alerts` | domain=None, hours=48, min_confidence=0.55, lang="en" | alerts list + domain_summary |
| `backtest_report` | product=None | test metrics, baselines, CI, per-class table |
| `forward_validation` | product=None | matured live predictions, running accuracy |

Example alert:
```json
{
  "article": {"title": "...", "source": "FMT", "url": "...", "published_at": "2026-10-09T10:20:00+08:00"},
  "product": "chicken",
  "direction": "UP",
  "probs": {"UP": 0.68, "DOWN": 0.07, "STABLE": 0.25},
  "triggers": ["feed cost", "shortage"],
  "price_context": {"change_7d_pct": 1.2, "change_30d_pct": 3.4, "data_as_of": "2026-10-08"},
  "explanation": {"headline": "...", "domain_impact": "...", "product_impacts": [], "confidence_note": "...", "disclaimer": "..."}
}
```

Tool rules: all tools return JSON. Never raise raw exceptions to the client. Return `{"error": "...", "hint": "..."}`. Log to stderr only (stdout breaks stdio MCP).

---

## 8. Data model (SQLite)

- `articles(id, url UNIQUE, title, source, published_at, summary, body, lang, fetched_at)`
- `article_products(article_id, product, match_score, matched_terms)`
- `predictions(id, article_id, product, direction, p_up, p_down, p_stable, model_version, created_at, horizon_days)`
- `outcomes(prediction_id, realized_ret, realized_label, scored_at)`

---

## 9. Non-functional
- Everything free. No paid API required.
- Runs on a laptop, 8 GB RAM, CPU only for inference.
- `scan_alerts` under 60 seconds for 48 hours of news (LLM calls dominate).
- Secrets in `.env`. Never commit.
- Model files versioned with `metrics.json` next to them.
- Unit tests for filter, label builder, price index, JSON schema.

---

## 10. Repo layout

```
mymarket/
  README.md
  PRD.md
  requirements.txt
  .env.example
  config/products.yaml
  config/sources.yaml
  data/raw/        (gitignored)
  data/processed/  (gitignored except small samples)
  models/          (model.joblib, label_map.json, metrics.json, thresholds.json)
  scripts/
    01_download_prices.py
    02_prepare_news.py
    03_build_price_index.py
    04_map_items.py
    05_build_examples.py
    validate_handoff.py
    demo.py
    daily_refresh.py
  # Training notebook is owned by the teammate in Google Colab.
  src/mymarket/
    ingest/ (rss.py, fetch_body.py)
    filter/ (aliases.py, embed_filter.py)
    prices/ (index.py, fuel.py)
    model/ (features.py, predict.py)
    llm/ (explain.py, prompts.py, schema.py)
    store/ (db.py)
    mcp_server.py
  tests/
```

---

## 11. Tech stack (all free)

Python 3.11, uv, pandas, pyarrow, scikit-learn, lightgbm, sentence-transformers, torch (CPU), feedparser, `scrapling[fetchers]`, httpx, tenacity, pydantic, pyyaml, rapidfuzz, joblib, python-dotenv, `mcp[cli]`, google-genai (or any OpenAI-compatible client for Groq/Ollama), pytest.

Free services: Kaggle, data.gov.my, Google Colab (T4), Google AI Studio, GitHub.

---

## 12. Milestones

Assumed 18 hours of work. I do not know your deadline. Compress by dropping v2 model and the fuel domain first.

| Phase | Work | Hours | Done when |
|---|---|---|---|
| P0 | Setup, repo, env | 1 | `pytest` runs, `.env` loads |
| P1 | Download news and prices, build daily index (data agent) | 3 | `data/processed/price_index.parquet` exists, plots look sane |
| P2 | Product mapping, examples, labels | 3 | `examples.parquet` with label counts per product |
| P3 | Train v0 and v1, evaluate | 3 | `metrics.json` with baselines |
| P4 | RSS ingest, Scrapling body, filter, predict | 3 | `predict_impact` works on a live URL |
| P5 | MCP server, LLM explainer | 3 | all 8 tools callable in Inspector |
| P6 | Forward validation, demo script, README | 2 | demo runs end to end |

---

## 13. Manual steps (you do these by hand)

Do them in order. Everything else the coding agent does.

### M0. Machine setup (20 min)
1. Install Python 3.11, Git, Node.js (needed only for MCP Inspector).
2. Terminal:
```bash
pip install uv
git clone <your repo> mymarket && cd mymarket
uv venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
uv pip install -r requirements.txt
```
3. If `scrapling` import fails with `ModuleNotFoundError`, run `scrapling install`. This downloads browsers. Skip it if imports work.

### M1. Get the Kaggle news dataset (15 min)
Option A, browser:
1. Log in at kaggle.com. Open the dataset page. Click Download. Unzip into `data/raw/news/`.

Option B, CLI:
1. Kaggle: profile picture, Settings, API section, Create New Token. A `kaggle.json` downloads.
2. Move it to `~/.kaggle/kaggle.json` (Windows: `C:\Users\<you>\.kaggle\kaggle.json`). On Mac/Linux run `chmod 600 ~/.kaggle/kaggle.json`.
3. If the page shows a different token format, follow the page.
4. Run:
```bash
uv pip install kaggle
kaggle datasets download -d azraimohamad/news-article-weekly-updated -p data/raw/news --unzip
```
5. Check: open one file, confirm the 12 columns, note min and max `published_date`, note row count. Write them in README. Keep `published_date >= 2020-01-01`.

### M2. Download price data (30 to 60 min, depends on internet)
1. Run `python scripts/01_download_prices.py`. It will:
   - download `lookup_item.parquet`, `lookup_premise.parquet`, `fuelprice.parquet`
   - loop `pricecatcher_YYYY-MM.parquet` from 2022-01 to current month
   - skip months that return 404 and print the first month found
   - keep one file in memory at a time, keep only mapped item codes, write a small daily table
2. Expect a few GB of downloads in total. Check free disk first. Raw files can be deleted after step 03.
3. Write the first available month in README. This sets your real training window.

### M3. Review product to item mapping (30 min)
1. Run `python scripts/04_map_items.py`. It writes `data/processed/item_mapping_review.csv` with proposed `item_code` per product.
2. Open in Excel. For each product, delete wrong rows. Example: "AYAM BERSIH" yes, "NUGGET AYAM" no.
3. Save as `config/item_mapping.csv`.
4. Rerun script 03 to build the price index.

### M4. Get an LLM key (10 min)
Gemini:
1. Go to aistudio.google.com/apikey. Sign in. Create API key.
2. Copy `.env.example` to `.env`. Set `LLM_PROVIDER=gemini`, `GEMINI_API_KEY=...`, `LLM_MODEL=<current flash-tier model name from the AI Studio model list>`.
3. Free tier has rate limits. Check them on the day.

Backup, no key: install Ollama, run `ollama pull llama3.2:3b` (or another small model), set `LLM_PROVIDER=ollama`. Slower, fully local.

### M5. Audit the relevance filter (45 min)
1. Run `uv run python scripts/audit_relevance.py export --size 120`. It writes `data/audits/relevance.csv` and a provenance sidecar from cached real alias candidates, including scores below 0.80.
2. Fill the existing `relevant` column with 1 or 0; only edit labels and optional notes. Relevant means the article concerns that product's price, costs, supply, or policy effects.
3. Run `uv run python scripts/audit_relevance.py assess`. Threshold selection uses tuning rows; article-grouped holdout rows assess the selected threshold. See MANUAL_STEPS.md for sample-size and precision gates.
4. Apply with `assess --apply` only when ready. If exclusions change or precision is poor, export a new sample with `--file`; small samples remain provisional. The audit does not measure alias recall or prediction accuracy.

### M6. Train on Colab (60 to 90 min)
1. Locally run scripts 05. Output: `data/processed/examples.parquet`. Check label counts printed per product. If a product has under 300 examples, merge it into a product group in `products.yaml` and rerun.
2. Make a Drive folder `mymarket`. Upload `examples.parquet`.
3. The teammate opens their training notebook at colab.research.google.com.
4. Runtime, Change runtime type, T4 GPU, Save.
5. Cell 1:
```python
from google.colab import drive
drive.mount('/content/drive')
!pip install -q sentence-transformers lightgbm scikit-learn pyarrow
```
6. Run the notebook cells in order:
   - load `examples.parquet`
   - embed text with `intfloat/multilingual-e5-small`, prefix `"query: "`, batch size 64
   - save embeddings `.npy` to Drive (Colab sessions disconnect)
   - train LogisticRegression and LightGBM with class weights
   - calibrate on validation split
   - evaluate on test and on rolling-origin quarters
   - write `model.joblib`, `label_map.json`, `thresholds.json`, `metrics.json`
7. Download the four files from Drive. Put them in `models/`.
8. Optional v2: run the fine-tune cell (3 epochs, learning rate 2e-5, max length 256). Keep it only if test macro-F1 beats v1.
9. If Colab is unavailable, coordinate with the teammate; this repository does not train models locally. Export all five files from `DATA_AGENT_PROMPT.md`, including the artifact manifest, then run `python scripts/validate_handoff.py` here.

### M7. Connect the MCP server (15 min)
1. Test first with Inspector:
```bash
npx @modelcontextprotocol/inspector uv run python -m mymarket.mcp_server
```
Open the URL it prints. Call `list_domains`, then `scan_alerts`.
2. Claude Desktop config file:
   - Mac: `~/Library/Application Support/Claude/claude_desktop_config.json`
   - Windows: `%APPDATA%\Claude\claude_desktop_config.json`
```json
{
  "mcpServers": {
    "mymarket": {
      "command": "uv",
      "args": ["--directory", "/ABSOLUTE/PATH/mymarket", "run", "python", "-m", "mymarket.mcp_server"]
    }
  }
}
```
3. Fully quit and reopen Claude Desktop. Check the tools icon.

### M8. Forward validation job (15 min)
1. Run once by hand: `python scripts/daily_refresh.py`. It downloads the current month price file, scans news, logs predictions, scores matured ones.
2. Schedule daily. Mac/Linux cron: `0 14 * * * cd /path/mymarket && .venv/bin/python scripts/daily_refresh.py`. Windows: Task Scheduler, daily 14:00.
3. PriceCatcher refreshes at 12:00 daily, so 14:00 is safe.

### M9. Demo prep (30 min)
1. Pick 2 past articles where the model was right and 1 where it was wrong. Show the wrong one. Judges trust honesty.
2. Screenshot the metrics table with baselines.
3. Rehearse the demo script below.

---

## 14. Success metrics

| Metric | Target | Note |
|---|---|---|
| Relevance precision (audit set) | at least 80% | M5 |
| Macro-F1 on time-split test | beat majority and momentum baselines | main claim |
| Alert precision at p >= 0.7 | report, no fixed target | honest number |
| End-to-end `scan_alerts` | under 60 s | 48 h news |
| Tools working in Inspector | 8 of 8 | |
| Forward validation | running, even if few matured rows | shows real check |

If the model does not beat momentum, say so. Then show it as "news context layer" with the keyword triggers and price context. Still a valid demo.

---

## 15. Risks

| Risk | Impact | Mitigation |
|---|---|---|
| RSS URL dead or changed | no live news | test each feed in browser, keep 3 or more sources, fallback to Scrapling on section pages |
| Site blocks scraping | no body text | use RSS summary, lower rate, never use stealth mode |
| Too few examples per product | weak model | merge products into groups, widen H to 28 days |
| Labels mostly STABLE | model predicts STABLE | per-product theta, class weights, tercile labeling option |
| LLM free quota hit | no explanations | template fallback, Ollama backup |
| Colab disconnect | lost work | save embeddings to Drive |
| Price file schema changes | pipeline breaks | schema check at load, clear error |
| Scope too big | miss deadline | drop fuel, drop v2, keep food only |

---

## 16. Demo script (5 minutes)

1. Open Claude Desktop. Ask: "What Malaysian news in the last 2 days could affect food prices?" Tool: `scan_alerts`.
2. Pick one alert. Ask: "Show the price trend for chicken." Tool: `price_context`.
3. Ask: "How accurate is this model?" Tool: `backtest_report`. Show baselines.
4. Ask: "How did past live predictions do?" Tool: `forward_validation`.
5. Close with limits: awareness only, weak signal, official CPI is the right inflation source.

---

## 17. Open questions for you

1. What is the hackathon deadline? It decides if fuel and v2 are in scope.
2. Must output support Malay? Default is English with optional `lang=ms`.
3. Does the judging rubric reward model accuracy or product usefulness? It changes how much time goes into P3 versus P5.

---

## 18. Team split (added 2026-10-10)

Two agents, two people, one contract.

| Track | Owner | Prompt file | Output |
|---|---|---|---|
| Data | Friend | `DATA_AGENT_PROMPT.md` | clean news, price index, item mapping, examples |
| App | You | `APP_AGENT_PROMPT.md` | live ingest, model code, MCP server, LLM explainer |

Contract files (schemas are in `DATA_AGENT_PROMPT.md`):
- `data/processed/news_clean.parquet`
- `data/processed/price_index.parquet`
- `config/item_mapping.csv`
- `data/processed/examples.parquet`

App track can start with fake sample files that follow the contract. Data track delivers the real ones.
