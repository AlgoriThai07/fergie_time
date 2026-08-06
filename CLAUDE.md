# CLAUDE.md

This file gives Claude Code persistent context for the FPL AI Agent project. Read it before starting any task. The full product/architecture plan lives in `docs/fpl-agent-plan.md` — treat it as the source of truth for scope and sequencing; this file is the condensed, implementation-facing version.

## What this project is

An AI-assisted Fantasy Premier League manager. It ingests FPL and news data, predicts player points, optimizes transfers/lineup/captaincy under real constraints, explains every recommendation with cited evidence, and can alert the user or auto-submit changes near a gameweek deadline if they haven't acted. Dual purpose: a tool the owner actually uses, and a portfolio-quality software engineering project.

## Core design principles (do not violate these without flagging it)

1. **The LLM never computes or decides.** Player point predictions come from a statistical/ML model. Transfer, lineup, and captaincy choices come from an ILP optimizer or deterministic rules. The LLM's only jobs are: (a) synthesizing/scoring news text for recency and credibility, and (b) explaining a decision the optimizer already made, grounded in real numbers from a tool call or DB record. If a task seems to need the LLM to "decide" or "calculate" something, stop and flag it — that's a design smell.
2. **Every recommendation must be explainable and evidence-linked.** No explanation text should state a number that isn't sourced from an actual model/optimizer output or DB record.
3. **No unnecessary infrastructure.** No microservices, no vector DB, no multi-agent framework unless a real, stated requirement demands it. Architecture 2 (single FastAPI app + Celery/Redis worker layer + Postgres) is the agreed target — don't drift toward Architecture 3 patterns.
4. **Auto-submit is the highest-risk feature.** It touches a real FPL account via undocumented, session-cookie-based write endpoints. Any code touching FPL write access must be idempotent, retryable, and tested against a secondary/test account before being pointed at the real one. Never hardcode or log session credentials.
5. **Baseline before upgrade, always.** Every model/algorithm component ships a simple, transparent baseline first (e.g. moving-average xP, greedy transfer heuristic) before the more sophisticated version, so improvements can be measured, not assumed.
6. **Backtesting must have no lookahead.** Any backtest or evaluation code must only use data that would have been available at that point in time — this is a correctness requirement, not a nice-to-have, and should have an explicit test.

## Deadline timing (exact, don't approximate)

- **T-1h30 before gameweek deadline**: if the user hasn't made changes/saved, fire a deadline alert (synthesize current news/price-change state).
- **T-30m before deadline**: if the user is *still* inactive, auto-submit fires and picks/submits the team, honoring the user's risk profile.
- These are two separate scheduled checks, not one — don't collapse them.

## Tech stack

- Backend: Python, FastAPI, SQLAlchemy, Alembic, Celery, Redis (broker + cache), Postgres
- Frontend: Next.js, React
- ILP: PuLP or OR-Tools (pick one early and stay consistent)
- LLM: Anthropic API via LangChain or direct SDK calls, tool-calling agent pattern
- Infra: Docker Compose locally, GitHub Actions CI/CD
- Testing: pytest (backend), fixture-based tests using saved sample FPL API payloads (don't hit the live API in tests)

## Repository structure

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
  docs/
    fpl-agent-plan.md      # full plan, source of truth for scope
    architecture.md
    design-decisions.md
  .github/workflows/
  README.md
```

## Conventions

- Python: type hints everywhere, `ruff` for lint/format, `pytest` for tests. Prefer explicit Pydantic schemas for API request/response models over loose dicts.
- SQLAlchemy models are the source of truth for schema; all schema changes go through an Alembic migration, never manual DB edits.
- Every Celery task must be idempotent — re-running it with the same inputs should not create duplicate side effects. This matters especially for ingestion and auto-submit.
- No FPL write-endpoint code should ever run against a real account without an explicit, separate confirmation step in the code path (not just "trust the caller").
- Don't reach for a new external dependency without checking if the existing stack (FastAPI/SQLAlchemy/Celery/PuLP) already covers it.
- Commit in small, reviewable units — one task from the sprint breakdown per commit/PR where reasonable.

## What's explicitly out of scope right now

No chip logic (wildcard/bench boost/free hit/triple captain), no multi-gameweek rolling planning, no Monte Carlo simulation, no adaptive-to-league-position strategy, no social/mini-league features, no mobile app, no other fantasy formats. Don't build toward these unless asked — they're documented future work, not silently-expected scope.

## Current phase

Sprint 2: baseline predictions and optimizer — player feature transform, baseline xP model (rolling average x fixture difficulty), first ILP optimizer (short-term only, no transfer-cost logic yet — that's Sprint 3), recommendations API + dashboard page. See `docs/sprint-2-tasks.md` for the broken-down task list. Sprint 1 (repo scaffolding, DB schema, read-only ingestion, basic squad dashboard, CI) is complete.