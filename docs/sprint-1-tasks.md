# Sprint 1 — Foundations

Goal: an end-to-end skeleton with real FPL data flowing into Postgres and showing up on a dashboard page. No intelligence yet (no xP model, no optimizer) — that's Sprint 2.

Do these in order. Each is small enough to be one Claude Code session/commit. Paste the prompt as-is (each already assumes `CLAUDE.md` is in the repo root and will be read automatically).

---

## Task 1.1 — Repo scaffolding

**Prompt:**
```
Set up the initial repository structure per CLAUDE.md. Create the full directory
tree (frontend/, backend/ with its subfolders, tests/, infra/, docs/,
.github/workflows/), a root README.md with a one-paragraph project description
and setup instructions, and a .gitignore appropriate for Python + Node.

Initialize:
- backend/ as a Python project (pyproject.toml or requirements.txt — your call,
  explain which and why briefly), with FastAPI, SQLAlchemy, Alembic, Celery,
  redis, pydantic, pytest, ruff as dependencies.
- frontend/ as a Next.js app (TypeScript, App Router) via create-next-app,
  minimal default page.

Don't write any business logic yet — this task is just getting a clean,
runnable skeleton in place. Confirm the backend can start with `uvicorn` and
serve a placeholder `GET /health` endpoint returning {"status": "ok"}, and the
frontend can start with `npm run dev` and render a placeholder page.
```

**Done when:** both apps boot locally, `/health` returns 200, repo structure matches CLAUDE.md.

---

## Task 1.2 — Docker Compose for local dev

**Prompt:**
```
Add infra/docker-compose.yml that runs: the FastAPI backend, a Postgres
container (with a named volume), and a Redis container. Add infra/Dockerfile.api
for the backend. Don't containerize the frontend yet — it can run via
`npm run dev` directly for now. Wire the backend's DB/Redis connection strings
to come from environment variables that match the docker-compose service names,
with sensible local defaults. Update the README with instructions to run
`docker compose up` from infra/ and have the API + Postgres + Redis come up
together, with /health reachable.
```

**Done when:** `docker compose up` from `infra/` brings up API + Postgres + Redis, and `/health` is reachable from the host.

---

## Task 1.3 — Core database schema (SQLAlchemy models + Alembic)

**Prompt:**
```
Implement the core SQLAlchemy models in backend/db/models.py per the schema in
docs/fpl-agent-plan.md section C ("Database schema (core tables)"). For Sprint 1
only implement the tables needed for ingestion and squad display:
users, players, teams, fixtures, gameweek_stats, user_squads,
user_transfer_state. Leave the rest (xp_predictions, recommendations,
recommendation_explanations, news_items, backtest_runs, auto_submit_log) as
noted TODOs with a one-line comment referencing which future sprint needs them
— don't implement them yet.

Set up Alembic in backend/db/migrations/ wired to these models, and generate
the initial migration. Add a short docs/architecture.md section (create the
file) documenting the schema decisions: why these tables, what's deferred and
why, keyed to the plan.
```

**Done when:** `alembic upgrade head` runs cleanly against the Postgres container and creates all listed tables.

---

## Task 1.4 — FPL API client (read-only)

**Prompt:**
```
Build a read-only FPL API client in backend/ingestion/fpl_client.py. It should
wrap these endpoints:
- bootstrap-static (players, teams, general data)
- fixtures
- entry/{team_id}/ and entry/{team_id}/event/{gw}/picks/ (a specific manager's
  squad for a given gameweek — no auth needed for this read-only data)

Design it as a small class with typed methods (e.g. get_bootstrap_static(),
get_fixtures(), get_entry_picks(team_id, gameweek)) returning parsed Pydantic
models, not raw dicts — define those models based on the actual shape of FPL's
JSON responses (look them up if you're not certain of the exact fields; note
any assumptions clearly in comments).

Do NOT implement anything related to write/transfer endpoints or session-cookie
auth in this task — read-only only, that's explicitly deferred to Sprint 5 per
CLAUDE.md.

Add unit tests in tests/unit/ that use saved sample JSON fixtures (create small
representative sample payloads by hand if you don't have real ones) rather than
hitting the live FPL API in tests.
```

**Done when:** the client can be called against the real FPL API and returns parsed, typed data; unit tests pass using local fixtures, not live calls.

---

## Task 1.5 — Ingestion task (populate raw tables)

**Prompt:**
```
Build a Celery task in backend/tasks/ingestion.py that uses the FPL client from
backend/ingestion/fpl_client.py to pull bootstrap-static and fixtures data and
upsert it into the players, teams, fixtures, and gameweek_stats tables. Set up
Celery + Celery beat configuration in backend/tasks/ (broker = Redis, per
CLAUDE.md), with this ingestion task scheduled to run daily for now (exact
near-deadline frequency logic comes in a later sprint).

The task must be idempotent — running it twice with the same source data should
not create duplicate rows or fail; use upsert semantics (e.g. merge on natural
key like fpl_id).

Add data validation: if the FPL API response is missing expected fields or
fails to parse, the task should log a clear error and skip that record (or
fail loudly for the whole batch, your call — explain the choice) rather than
silently writing malformed data.

Add an integration test that runs this task against a test Postgres DB with
mocked FPL client responses (use the fixtures from Task 1.4) and asserts the
expected rows exist afterward, and that running it twice doesn't duplicate rows.
```

**Done when:** running the task against a real (or fixture-backed test) FPL response populates the DB correctly and idempotently; integration test passes.

---

## Task 1.6 — Squad API endpoint

**Prompt:**
```
Add a FastAPI endpoint GET /squad/{user_id} in backend/api/ that returns the
user's current squad: the 15 players, their team/position/price, and which are
starting vs bench, per the user_squads table. For now, since we don't have a
real multi-user auth flow yet, accept a raw FPL entry ID as user_id and, if
there's no matching row in user_squads yet, fetch it live via
get_entry_picks() from the FPL client (from Task 1.4) as a fallback, persist
it, and return it — don't block this endpoint on the full ingestion pipeline
being done first.

Define a clear Pydantic response schema. Add an API contract test asserting the
response shape.
```

**Done when:** hitting `GET /squad/{your_real_fpl_entry_id}` returns your actual current squad.

---

## Task 1.7 — Dashboard squad page

**Prompt:**
```
In the Next.js frontend, build a simple squad page that calls
GET /squad/{user_id} (hardcode a user_id input field or query param for now —
no auth yet) and displays the 15 players grouped by position, showing name,
team, price, and starting/bench status. Keep styling minimal and clean — this
is a functional skeleton, not the final UI. No need for the design system
polish yet; correctness and clarity over aesthetics for this task.
```

**Done when:** loading the page with a real FPL entry ID shows your actual squad, matching what Task 1.6 returns.

---

## Task 1.8 — CI pipeline

**Prompt:**
```
Add a GitHub Actions workflow in .github/workflows/ that runs on every push/PR:
ruff lint + format check on backend/, pytest on backend/tests/ (unit +
integration, spinning up Postgres and Redis as service containers for the
integration tests), and a basic `npm run build` check on frontend/ to catch
type errors. Keep it simple — one workflow file, clear job names, fail fast on
lint before running tests.
```

**Done when:** a PR triggers the workflow and it passes on the current state of the repo.

---

## After Sprint 1

Once all 8 tasks are done and merged, you should be able to: run `docker compose up`, see a real Postgres populated with your actual FPL players/teams/fixtures/squad, and view your live squad on a (rough) dashboard page — with CI green. That's the Sprint 1 "definition of done" from the main plan. Come back before starting Sprint 2 (baseline xP model + first ILP optimizer) if you want to sanity-check the schema or client design first.