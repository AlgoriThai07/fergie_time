# FPL AI Agent — Implementation Plan

Architecture 2 (portfolio-optimized): FastAPI + Next.js + Celery/Redis worker layer + Postgres.

---

## A. Product definition

**Name ideas**: Pitchside, SquadCast, Gaffer, FixtureIQ, Auto-XI

**One-sentence pitch**: An FPL assistant that predicts player points, optimizes your squad under real constraints, explains every recommendation with evidence, and can safely act on your behalf when you don't.

**Target user**: Any FPL manager who wants data-driven decisions and is willing to trust an assistant once it's proven itself via backtesting.

**Core problem**: Weekly FPL decisions (transfers, captaincy, lineup) are a constrained optimization problem under uncertainty, but most managers make them by gut feel or by reading fragmented advice across multiple sites.

**Unique value proposition**: Combines an exact optimizer (not a heuristic or an LLM guess) with a transparent, evidence-cited explanation for every decision, and a track record you can independently verify via backtesting.

**Main user flow**: User connects FPL account → dashboard shows current squad + xP-based recommendations → user reviews explanation → approves, or gets alerted at T-1h30 if still inactive, and if still inactive at T-30m auto-submit acts on their behalf → after the gameweek, results feed back into the backtest record.

**MVP boundaries**: Single-user-tested, multi-tenant-capable. Transfers + lineup only (no chips). Static risk profile (balanced/aggressive), not adaptive to league position.

**Non-goals**: No social/mini-league features, no mobile app, no other fantasy formats/sports, no scaling/monetization concerns.

---

## B. Functional requirements

**Must have**
- Ingest FPL bootstrap/fixtures/entry data on a schedule
- xP baseline model (rolling average + fixture difficulty)
- ILP optimizer: transfers (short+long horizon, transfer-cost aware) + starting XI/bench
- Captaincy ranking (xP sort, baseline)
- Grounded LLM explanation for every recommendation
- Chat agent with read-only tools for "why" questions
- Deadline alerting (T-1h30, if still inactive)
- Auto-submit if inactive, respecting a user-set risk profile
- Backtesting framework against historical gameweeks
- Free-transfer state tracking per user (banked count, cap 5)

**Should have**
- xP ML model upgrade (vs. baseline, with comparison)
- News recency/credibility scoring pipeline
- Risk-adjusted captaincy (variance-aware)
- Confidence scores (optimizer-margin based)
- Guardrails/overrides (e.g. "never auto-sell my highest-owned player")

**Could have**
- Prediction-interval-based confidence (vs. optimizer-margin proxy)
- Multiple secondary/test FPL accounts for safe auto-submit testing

**Future work**
- Chip timing (wildcard, bench boost, free hit, triple captain)
- Multi-gameweek rolling-horizon planning
- Monte Carlo simulation for differential/chip decisions
- Adaptive strategy based on league position

---

## C. Technical architecture

**System context**: Next.js dashboard (reads + approvals) ↔ FastAPI (sync API + chat agent) ↔ Postgres (system of record) + Redis (cache + Celery broker) ↔ Celery workers (ingestion, xP, ILP, news scoring, auto-submit) ↔ external FPL API (read/write) + news sources.

**Service boundaries**: Single FastAPI app (API + agent, both need low latency, share request context). Single Celery worker pool, task-routed by queue name (`ingestion`, `compute`, `submit`) so the deadline-critical submit task isn't blocked behind slower ingestion jobs.

**Data flow**: Scheduled ingestion → raw tables → transform to processed/feature tables → xP model reads processed tables → ILP reads xP output + user squad state → recommendation persisted → explanation generated on read (or cached) → dashboard/agent read recommendation + explanation.

**Database schema (core tables)**
- `users` (id, fpl_entry_id, risk_profile, encrypted_session_token)
- `players` (id, fpl_id, name, team_id, position, price, ...)
- `teams` (id, fpl_id, name)
- `fixtures` (id, gameweek, home_team_id, away_team_id, difficulty_home, difficulty_away, kickoff_time, status)
- `gameweek_stats` (player_id, gameweek, minutes, goals, assists, xg, xa, bonus, total_points) — raw per-GW performance
- `xp_predictions` (player_id, gameweek, predicted_points, model_version, confidence)
- `user_squads` (user_id, gameweek, player_id, is_starting, is_captain, is_vice)
- `user_transfer_state` (user_id, gameweek, free_transfers_banked, bank_balance)
- `recommendations` (id, user_id, gameweek, type [transfer/lineup/captain], payload_json, created_at)
- `recommendation_explanations` (recommendation_id, explanation_text, citations_json)
- `news_items` (id, player_id, source, raw_text, published_at, ingested_at, confidence_tag [confirmed/doubtful/rumor])
- `backtest_runs` (id, gw_range, model_version, total_points, baseline_points, created_at)
- `auto_submit_log` (id, user_id, gameweek, status, submitted_payload, error_detail, submitted_at)

**API endpoints (representative)**
- `GET /squad/{user_id}` — current squad + state
- `GET /recommendations/{user_id}/{gameweek}` — latest transfer/lineup/captain recs + explanations
- `POST /recommendations/{user_id}/{gameweek}/approve` — user approves and triggers submission
- `POST /chat` — agent turn (tool-calling)
- `GET /backtests?gw_start=&gw_end=` — backtest results
- `GET /players/{id}/news` — news items for a player, with confidence tags
- `PATCH /users/{id}/risk-profile` — update risk profile

**Background processing**: Celery beat schedules — full ingestion (daily), news scan (every few hours, more frequent near deadline), deadline alert (fires at T-1h30 if user still inactive), auto-submit check (fires at T-30m, idempotent, retries with backoff, hard cutoff before actual deadline, only proceeds if still inactive at that point).

**Caching strategy**: Redis cache on FPL bootstrap-static/fixtures (short TTL, since prices/status change during the day) and on computed xP for a given gameweek (invalidate on new ingestion). Track cache hit rate as a metric.

**Agent tools**: `get_squad_state`, `get_recommendation`, `get_player_news`, `get_backtest_result` — all read-only, all returning structured data the LLM narrates.

**Model interfaces**: xP model exposes `predict(player_id, gameweek) -> (point_estimate, confidence)`; ILP optimizer exposes `optimize(squad, budget, constraints, xp_map, free_transfers) -> recommendation`. Both are swappable behind these interfaces so the baseline can be replaced by the ML upgrade without touching the optimizer or API layer.

**Failure handling**: Ingestion failures logged and alerting fires if a scheduled job fails N times in a row; ILP infeasibility (shouldn't happen given valid constraints, but defensively) falls back to "no recommended change" rather than crashing; auto-submit failures fall back to a notification instead of silently failing, and never partially submit (all-or-nothing transfer batch).

**Authentication and security**: FPL session tokens encrypted at rest, decrypted only inside the submit worker, never returned via API/logs. Standard user auth (email/password or OAuth) for the dashboard itself, separate from FPL session credentials.

**Observability**: Structured logs (JSON) for every task run with status/duration; basic metrics — task success rate, queue depth, ILP solve time, cache hit rate — exported to a lightweight dashboard (hosted Grafana Cloud free tier or similar, not self-hosted Prometheus at this scale).

---

## D. Agent design

- **Objective**: answer open-ended "why"/"what if" questions about squad state and recommendations, grounded entirely in tool results.
- **Available tools**: `get_squad_state`, `get_recommendation`, `get_player_news`, `get_backtest_result` (all read-only; no submit/override tool).
- **Agent state**: mostly stateless — each turn re-fetches fresh data via tools rather than relying on conversation memory for facts.
- **Memory strategy**: short conversational context window only (recent turns), no long-term memory store for MVP.
- **Planning process**: single-agent, tool-calling loop (fetch → reason → respond); no multi-step planning framework needed given the tool set's simplicity.
- **Approval checkpoints**: every recommendation requires explicit user approval unless auto-submit's inactivity condition is met; auto-submit itself is a deterministic workflow, not an agent decision.
- **Retry and timeout behavior**: Celery task-level retries with exponential backoff for ingestion/submit tasks; agent chat calls have a hard timeout with a graceful "couldn't complete that, try again" fallback.
- **Guardrails**: agent has no write tools; explanation generation is instructed to never state a number not sourced from a tool call.
- **Structured output schemas**: recommendation explanations follow a schema — `{claim, supporting_data_ref}` pairs — so groundedness is programmatically checkable.
- **Hallucination reduction**: schema enforcement + tool-only-facts instruction + (stretch) automated check that every numeric claim in an explanation matches a value in the referenced tool result.
- **Evidence citation**: every explanation references the specific xP values, fixture difficulty, or news item that drove the recommendation, surfaced in the UI as expandable detail.
- **Design choice**: single agent with tools, synchronous within the FastAPI process — no multi-agent architecture, no separate agent microservice; not justified by the actual complexity here.

---

## E. Data and modeling

**Data sources**: FPL API (bootstrap-static, fixtures, entry — read; transfers/lineup — write), Understat/FBref (optional xG/xA enrichment), football-data.org (fixture backup/cross-check), scraped press-conference/team-news roundups (Premier Injuries, Fantasy Football Scout).

**Ingestion schedule**: full data pull daily; news scan every few hours, increasing in frequency as a gameweek deadline approaches; final news check at T-1h30 (feeds the inactivity alert) and again at T-30m (feeds auto-submit, if still inactive).

**Raw and processed tables**: raw ingestion lands in `gameweek_stats`/`fixtures`/`news_items` as close to source shape as practical; a transform step derives model-ready features (rolling averages, fixture-difficulty-adjusted metrics) into a `player_features` table.

**Feature engineering**: rolling N-gameweek point average, minutes trend, fixture difficulty (upcoming N), home/away split, (optional) xG/xA rolling averages.

**Model baseline**: rolling average points × fixture-difficulty multiplier — transparent, no training required, ships first.

**Improved model**: gradient-boosted regression (e.g. LightGBM) over the engineered features, trained on historical seasons, versioned (`model_version` in `xp_predictions`) so backtests can compare versions directly.

**Optimization algorithm**: ILP over squad/budget/formation constraints, objective = short-term xP gain + long-term xP gain − transfer-hit cost, with confidence-based decay weighting on longer horizons.

**Backtesting methodology**: replay historical gameweeks — feed the model/optimizer only data that would have been available at that point in time (no lookahead), compare recommended vs. actual outcomes, and compare against (a) doing nothing, (b) the FPL average manager score for that gameweek.

**Evaluation metrics**: MAE for xP model vs. baseline; total backtested points vs. baseline/average manager; ILP solve time; auto-submit success rate.

**Handling missing/stale data**: if a data source fails, ingestion falls back to the last successfully cached values and flags staleness; the optimizer and explanation layer should surface "data may be stale" rather than silently proceeding on old data for critical near-deadline decisions.

---

## F. Development roadmap

### Sprint 1 — Foundations
- **Goal**: end-to-end skeleton with real data flowing, no intelligence yet.
- **Backend**: FastAPI skeleton, Postgres schema (core tables), ingestion task for FPL bootstrap/fixtures/entry data.
- **Frontend**: Next.js shell, squad display page reading from the API.
- **Data**: raw ingestion tables populated, basic validation on ingest.
- **Infra**: Docker Compose (API, worker, Postgres, Redis), CI running lint + basic tests.
- **Tests**: ingestion parses real FPL API responses correctly (fixture-based tests against saved sample payloads).
- **Definition of done**: dashboard shows your real current squad, pulled live from FPL.
- **Demoable result**: "here's my squad, live from the FPL API."

### Sprint 2 — Baseline predictions and optimizer
- **Goal**: first real recommendations, using the simplest honest model.
- **Backend**: baseline xP model (rolling avg × FDR), ILP optimizer (transfers + lineup, short-term only, no transfer-cost logic yet).
- **Frontend**: recommendations page showing suggested transfer + lineup.
- **Data**: `player_features` transform job, `xp_predictions` table populated.
- **Infra**: Celery + Redis wired in for the compute tasks.
- **Tests**: ILP correctness tests (respects budget/formation/club-limit constraints on synthetic inputs).
- **Definition of done**: optimizer produces a valid, constraint-respecting recommendation from real data.
- **Demoable result**: "here's what the optimizer suggests for my squad, and why it's a valid team."

### Sprint 3 — Explanations and transfer economics
- **Goal**: recommendations become trustworthy, not just numbers.
- **Backend**: transfer-cost-aware ILP objective (short/long horizon, free-transfer state tracking), grounded LLM explanation generation.
- **Frontend**: explanation panel per recommendation (short-term/long-term breakdown).
- **Data**: `user_transfer_state` table + logic.
- **Tests**: explanation groundedness check (claims trace to real data).
- **Definition of done**: every recommendation has a persisted, evidence-linked explanation.
- **Demoable result**: "here's why this transfer is recommended, broken into short- and long-term value."

### Sprint 4 — News, alerting, and the chat agent
- **Goal**: proactive, conversational layer on top of the working core.
- **Backend**: news scraping + recency/confidence scoring pipeline, deadline alert task (fires at T-1h30 if still inactive), chat agent with read-only tools.
- **Frontend**: chat interface, alert notifications.
- **Data**: `news_items` table + confidence tagging.
- **Tests**: agent tool-call tests (mocked tool responses → correct grounded answer).
- **Definition of done**: you get a real deadline alert with current news synthesized; you can ask the chat "why" and get a grounded answer.
- **Definition of done**: alerts fire correctly in a staging run.
- **Demoable result**: "it messaged me before deadline with what changed, and I asked it why and got a straight answer."

### Sprint 5 — Auto-submit
- **Goal**: the highest-risk, highest-signal feature, built carefully.
- **Backend**: FPL session-auth handling (encrypted storage), submit task (fires at T-30m only if the T-1h30 alert went unheeded, idempotent, retryable), risk-profile-driven fallback logic, `auto_submit_log`.
- **Frontend**: risk-profile setting, auto-submit status/history view.
- **Infra**: task routing so submit queue is isolated and prioritized near deadlines.
- **Tests**: submit task tested against a sandbox/secondary account first, idempotency test (running twice doesn't double-submit).
- **Definition of done**: a real gameweek deadline passes with auto-submit correctly acting (tested on a secondary account before your main one).
- **Demoable result**: "I ignored the deadline on purpose and it picked my team for me, and logged exactly why."

### Sprint 6 — ML model upgrade and backtesting
- **Goal**: prove the system actually works, and improve it with evidence.
- **Backend**: gradient-boosted xP model, backtesting framework (replay historical gameweeks, no-lookahead guarantee).
- **Frontend**: backtest results page (model vs. baseline vs. average manager).
- **Data**: historical season data ingestion for backtesting.
- **Tests**: backtest no-lookahead test (model can't see future data at any replayed point).
- **Definition of done**: a documented, reproducible backtest report comparing model versions.
- **Demoable result**: "here's the evidence this actually beats a naive baseline, across a real season."

### Sprint 7 — Polish and deployment
- **Goal**: production-ready, presentable.
- **Backend**: risk-adjusted captaincy, confidence scores, guardrail settings.
- **Frontend**: dashboard polish, metrics visible in-app.
- **Infra**: production deployment (cloud), CI/CD, monitoring/alerting live.
- **Tests**: end-to-end test of full weekly cycle, load test on API endpoints.
- **Definition of done**: deployed, monitored, and running unattended for a full live gameweek.
- **Demoable result**: the finished product, live, with a real season of backtested proof behind it.

---

## G. Repository structure

Single monorepo — the frontend/backend/worker/model code are tightly coupled (shared schema, shared types where possible) and a single student maintaining this benefits far more from one repo, one CI pipeline, and atomic cross-cutting commits than from multi-repo coordination overhead.

```
fpl-agent/
  frontend/                # Next.js app
  backend/
    api/                   # FastAPI routes
    agent/                 # tool-calling agent, tool definitions
    optimization/          # ILP optimizer
    models/                # xP model(s), baseline + ML
    ingestion/              # scheduled ingestion tasks
    tasks/                  # Celery task definitions, beat schedule
    db/
      migrations/          # Alembic migrations
      models.py            # SQLAlchemy models
  tests/
    unit/
    integration/
    backtests/
  infra/
    docker-compose.yml
    Dockerfile.api
    Dockerfile.worker
    terraform/ (or equivalent, if used)
  docs/
    architecture.md
    design-decisions.md
  .github/workflows/       # CI/CD
  README.md
```

---

## H. Testing plan

- **Unit tests**: xP feature engineering functions, ILP constraint construction, news confidence tagging logic.
- **Integration tests**: ingestion → DB → xP → ILP → recommendation, run against a test DB with fixture data.
- **API contract tests**: schema validation on all endpoints (request/response shape).
- **Data validation tests**: ingestion rejects/flags malformed FPL API responses rather than silently corrupting data.
- **Agent tool tests**: mocked tool responses produce correctly grounded, schema-conformant explanations.
- **Model evaluation**: MAE tracked per model version against a held-out historical set.
- **Optimization correctness**: ILP respects all constraints (budget, formation, max-3-per-club) on synthetic edge cases (e.g. tight budget, near-cap club counts).
- **End-to-end tests**: full weekly cycle simulated (ingest → recommend → approve/auto-submit → log) against a staging environment.
- **Load tests**: basic throughput check on the dashboard/API endpoints (not a major focus given real scale, but worth a baseline number).
- **Backtesting**: no-lookahead correctness (model cannot access future gameweek data when evaluated at a past point), and its own numeric outputs treated as a test category, not just a report.

---

## I. Deployment plan

- **Local development**: Docker Compose (API, worker, Postgres, Redis, frontend dev server).
- **Environments**: separate dev/staging and production configs; staging used specifically to test auto-submit against a secondary FPL account before trusting production with your main one.
- **Secrets management**: environment-based secrets (cloud provider's secret manager or even encrypted `.env` for a project this size), FPL session tokens additionally encrypted at the application layer.
- **Database migrations**: Alembic, run as a CI/CD step before deploy.
- **CI/CD**: GitHub Actions — lint, test, build, deploy on merge to main; migration step gated before app deploy.
- **Cloud services**: small managed Postgres (e.g. RDS free/small tier or a managed Postgres provider), small compute for API + worker (single small instance or two — no need for autoscaling groups at this scale), managed Redis (small instance).
- **Monitoring and alerting**: structured logs shipped somewhere queryable, basic dashboard for the metrics from Phase 4, alert (even just an email/webhook) if the deadline auto-submit task fails.
- **Cost-conscious alternatives**: Railway/Fly.io/Render as a single-provider alternative to piecing together AWS services, meaningfully cheaper and simpler for a project at this scale while still being a legitimate, explainable infra choice.

---

## J. Recruiter presentation

- **README**: clear problem statement, architecture diagram, live demo link, backtest results front and center (not buried).
- **Architecture diagram**: the Architecture 2 diagram, plus a data-flow diagram for the transfer-recommendation pipeline specifically.
- **Demo video**: 2–3 minutes — show a real recommendation, its explanation, a chat "why" exchange, and the backtest results page.
- **Live application**: deployed and running against your real account (or a demo account) so recruiters can see it working, not just read about it.
- **Technical design document**: a condensed version of this plan — decisions, tradeoffs, and the honest "what I'd do differently" section.
- **Engineering metrics**: the Phase 4 metrics, with real numbers once available — MAE vs. baseline, backtested points vs. average manager, cache hit rate, auto-submit reliability.
- **Resume bullets**: e.g. "Built an ILP-based transfer optimizer with a horizon-aware objective function, backtested against N historical gameweeks, outperforming a naive baseline by X%." / "Designed a deadline-critical, idempotent task pipeline (Celery/Redis) achieving X% successful unattended execution across N gameweeks." / "Built a grounded LLM explanation layer with structured claim-to-evidence citation, avoiding hallucinated recommendations."

**Three strong interview stories to prepare**:
1. **Tradeoff story**: why ILP instead of an LLM or heuristic for transfer selection — the "worst tool that still works" framing, and what you'd lose by picking either alternative.
2. **Reliability story**: designing the auto-submit pipeline to be safe under a hard deadline — idempotency, retries, fallback behavior, and how you tested it without risking your real account.
3. **Debugging/evaluation story**: a real case from backtesting where the ML model underperformed the baseline (or overfit), what you found, and how you fixed or explained it — this is the strongest kind of story because it shows judgment under an honest negative result, not just a polished success.

---

## Open assumptions / unresolved questions to revisit during implementation

- Exact confidence-decay function for long-horizon xP weighting (needs empirical tuning once real backtest data exists).
- Whether optimizer-margin confidence is good enough for MVP guardrails, or whether prediction intervals are needed sooner than planned.
- Cloud provider choice (AWS vs. Railway/Fly.io) — deferred to Sprint 7, revisit based on actual cost/complexity tradeoff at that point.
- Whether a secondary/test FPL account is available for safely testing auto-submit before Sprint 5.