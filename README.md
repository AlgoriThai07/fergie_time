# FergieTime

FergieTime is an AI-assisted Fantasy Premier League (FPL) manager application designed to optimize weekly decisions under budget and transfer constraints. By combining statistical and machine learning models for player point predictions with an exact integer linear programming (ILP) optimizer, the application recommends transfer, captaincy, and starting lineup actions. An LLM-powered explanation engine synthesizes relevant news and details the underlying rationale for every decision. FergieTime also features automated deadline alerting and optional, guarded auto-submission to the FPL API when users are inactive near gameweek deadlines.

## Repository Structure

Per [CLAUDE.md](CLAUDE.md), the repository structure is:

- `frontend/`: Next.js web application (TypeScript, App Router).
- `backend/`: FastAPI backend and core ML/optimization scripts.
  - `api/`: REST endpoints.
  - `agent/`: LLM tool-calling agent.
  - `optimization/`: ILP optimizer.
  - `models/`: Point prediction models.
  - `ingestion/`: FPL API ingestion client and sync logic.
  - `tasks/`: Celery tasks and scheduling.
  - `db/`: Database schemas and migrations.
- `tests/`: Unit, integration, and backtest suites.
- `infra/`: Local deployment infrastructure (Docker Compose, Dockerfiles).
- `docs/`: Design and architectural documentation.

## Setup Instructions

### Prerequisites
- Python 3.11+
- Node.js 18+ and npm
- Docker and Docker Compose

### Running with Docker Compose (Recommended for Backend)
You can run the FastAPI backend, Postgres database, and Redis cache together using Docker Compose:
1. Navigate to the `infra/` directory:
   ```bash
   cd infra
   ```
2. Build and start the services:
   ```bash
   docker compose up --build
   ```
   This will spin up:
   * **API Service** on `http://localhost:8000` (health check at `http://localhost:8000/health`)
   * **Postgres Database** on port `5432` (persisted via `postgres_data` volume)
   * **Redis Cache** on port `6379`

### Local Backend Setup (Alternative)
1. Navigate to the `backend/` directory:
   ```bash
   cd backend
   ```
2. Create and activate a virtual environment:
   ```bash
   python -m venv .venv
   # Windows:
   .venv\Scripts\activate
   # macOS/Linux:
   source .venv/bin/activate
   ```
3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
4. Start the backend development server:
   ```bash
   uvicorn api.main:app --reload
   ```
   The health check will be live at `http://127.0.0.1:8000/health`.

### Frontend Setup
1. Navigate to the `frontend/` directory:
   ```bash
   cd frontend
   ```
2. Install dependencies:
   ```bash
   npm install
   ```
3. Start the development server:
   ```bash
   npm run dev
   ```
   The web application will be live at `http://localhost:3000`.
