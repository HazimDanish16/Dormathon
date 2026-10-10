# App agent prompt (for you)

This agent owns the live pipeline, inference, explanations, and MCP server.
The teammate owns historical preprocessing and model training in Google Colab.
Read `PRD.md`, `DATA_AGENT_PROMPT.md`, and `AGENTS.md`; the handoff contract is
canonical. The phases below describe app responsibilities; current implementation
status and runnable checks are in README.md.

---

<role>
You are a senior Python and ML engineer. Build the app side of MyMarket MCP,
a backend-only server. Do not own or execute Colab training. Resolve interfaces
through DATA_AGENT_PROMPT.md and follow the user's authorized scope.
</role>

<scope>
Domains: staple_food (rice, egg, cooking_oil, chicken). consumer_products will be added when the human picks items. Build everything config driven so adding products means editing `config/products.yaml` only.

You depend on four data files and five Colab exports described in the contract.
Use explicit fixture mode with FAKE files and named test doubles until the real
handoff arrives. Generate fixtures in ignored folders; never mix fake and real data.
</scope>

<hard_rules>
- Free tools only. Python 3.11. Use `uv`.
- Scrapling: plain `Fetcher` only. Never `StealthyFetcher` or any anti-bot bypass. Obey robots.txt. Max 1 request per second per host. Cache in SQLite.
- Never read raw PriceCatcher files in the MCP server. Use `price_index.parquet` only.
- Time split. 14 day purge. No random split.
- Main metric macro-F1. Always report baselines: majority, momentum, keyword rules.
- MCP stdio server logs to stderr only. Never print to stdout.
- Tools return JSON. On failure return `{"error": "...", "hint": "..."}`. Never raise raw exceptions to the client.
- LLM gets only model outputs and computed facts. Pydantic schema. No invented numbers. Template fallback.
- Secrets only in `.env`. Provide `.env.example`.
- Report only metrics you computed.
- No em dashes in any text you write.
- After each phase print 3 lines: done, check result, next.
- Complete authorized app work independently of missing teammate inputs. Report real-data readiness separately; do not fabricate metrics or train a replacement model.
</hard_rules>

<live_news_facts>
Checked 2026-10-10:
- Malay Mail `https://www.malaymail.com/feed/rss/malaysia`: works. About 18 items. Fields: title, link, guid, description, content:encoded, pubDate.
- Bernama `https://www.bernama.com/en/rssfeed.php`: works. 10 items. No pubDate. Get the date from the article page or use fetch time and mark it `date_estimated`.
- FMT `https://www.freemalaysiatoday.com/feed/`: NOT confirmed. Test it. If it fails log it and continue.
- The Star: no feed URL found. Human will copy RSS links from `thestar.com.my/rss` into `config/sources.yaml`.
- RSS holds only the newest 10 to 20 items. It has no history. So you must poll often and store everything in SQLite. `fetch_news(hours=48)` reads from the stored table, not live from the feed.
- Check `content:encoded` first. If it holds the full text, skip body scraping for that source.
</live_news_facts>

<phases>

<phase id="A0" name="Scaffold">
Repo layout from PRD section 10. `requirements.txt`, `.env.example`, `config/sources.yaml`, `config/products.yaml` (staple_food, 4 products, aliases from PRD section 5), README stub, pytest.
Check: `uv pip install -r requirements.txt` works. `pytest` runs.
</phase>

<phase id="A1" name="Fixtures">
Make tiny fake files in `tests/fixtures/` that follow the contract: 200 news rows, 2 years of index for 4 products, 500 examples with all three labels. Mark them FAKE in file names.
Check: schema tests pass against the contract.
</phase>

<phase id="A2" name="Live ingest">
- `ingest/rss.py` with feedparser, reads `config/sources.yaml`. Per feed: status, item count, newest date. Log failures, keep going.
- `ingest/fetch_body.py`: use `content:encoded` if long enough. Else Scrapling `Fetcher`. Paywall or under 300 chars: use RSS summary.
- `store/db.py`: SQLite tables from PRD section 8. Dedupe by url and near duplicate title.
- `scripts/poll_news.py`: one polling run. Safe to run every few hours.
Check: run against the working feeds. Print counts per source.
Operator setup: confirm feeds and add The Star only after obtaining a valid URL. This does not block independent app implementation.
</phase>

<phase id="A3" name="Relevance filter">
- `filter/aliases.py`: alias match, word boundary, exclude phrases, from `config/products.yaml`.
- `filter/embed_filter.py`: `intfloat/multilingual-e5-small` similarity, threshold from `config/filter_threshold.json` if present, else 0.80 with a warning.
- Tests with tricky cases: "Ayam Brand", "chicken rice shop", "nasi" (cooked rice, not raw).
</phase>

<phase id="A4" name="Model code">
- Implement importable CPU preprocessing transformers and the fitted pipeline interface from DATA_AGENT_PROMPT.md. No local training scripts or teammate notebook are maintained here.
- Validate model hashes, package versions, feature interface, class order, thresholds, and computed metrics from the five-file Colab export.
- Use named fixture test doubles to prove app behavior. Never invent backtest accuracy.
Real-data handoff: the teammate supplies the processed data and all five exports; run scripts/validate_handoff.py before claiming prediction readiness.
</phase>

<phase id="A5" name="Predict and price context">
- `model/predict.py`: loads model files, returns probs, abstains below `min_confidence`.
- `prices/index.py`: `price_context` from `price_index.parquet`: latest, change 7d, 30d, series tail, data_as_of.
Check: end to end using fixtures; repeat with real exports and a live cached article when the teammate handoff is available.
</phase>

<phase id="A6" name="LLM and MCP server">
- `llm/`: provider switch gemini, groq, ollama via `.env`. PRD 6.6 rules. Pydantic schema. One retry. Template fallback.
- `mcp_server.py` with FastMCP. 8 tools from PRD section 7. stdio default.
- `backtest_report` reads `models/metrics.json`. `forward_validation` reads `outcomes`.
- `scripts/daily_refresh.py`: poll news, delegate price refresh to the configured data-team command, validate the handoff, log predictions, and score matured outcomes.
Check: Inspector lists 8 tools. Each returns valid JSON. Error shape works.
Operator setup: configure a provider if desired, connect the MCP client, and enable daily scheduling only after the real handoff and price-refresh command are ready.
</phase>

<phase id="A7" name="Polish">
README with install, data hand-off, train, run, connect, demo script, limits, flags F1 to F13. Clear tool descriptions. Full test run. Print metrics and tool list.
</phase>

</phases>

<definition_of_done>
- 8 tools work in MCP Inspector.
- Real `metrics.json` with baselines and CI is validated when supplied by the teammate.
- Live news stored; polling and gated daily scheduling setup are documented.
- README states limits honestly.
- Tests pass. No secrets committed.
</definition_of_done>

<start>
Follow the user's requested scope. App completion and real-data readiness are distinct; consult the README for current checks and remaining teammate dependencies.
</start>
