# Architectural Documentation

## Database Schema Design (Sprint 1)

In Sprint 1, we implemented the core FPL system tables required for data ingestion and roster display.

### Core Tables Implemented

1. **`users`**:
   - Represents the FPL application users.
   - Stores `risk_profile` (e.g., balanced, aggressive) which determines the threshold for auto-submission backup logic, and the `encrypted_session_token` for authenticated writes to the FPL API.
2. **`teams`**:
   - Stores general Premier League club information (e.g., Arsenal, Chelsea).
   - Maps directly to the FPL team identifier using `fpl_id` as the natural key.
3. **`players`**:
   - Stores individual player info (web name, position, team, current price).
   - Price is stored as an integer in tenths of a million (e.g., `55` represents `£5.5m`) to avoid floating-point rounding errors during constraints calculations.
4. **`fixtures`**:
   - Tracks home/away pairings, kickoff times, game status, and FDR (Fixture Difficulty Rating) for both home and away teams.
   - Crucial for the xP prediction models.
5. **`gameweek_stats`**:
   - Captures player performance stats on a per-gameweek basis (goals, assists, xG, xA, total points).
   - Supports natural key indexing on `(player_id, gameweek)`.
6. **`user_squads`**:
   - Maps users to their 15-player squads for a given gameweek, including starting/bench status and captaincy status.
7. **`user_transfer_state`**:
   - Tracks a user's transfer economics (banked free transfers, remaining bank balance) on a per-gameweek basis.

### Deferred Tables

To remain strictly aligned with Sprint 1 boundaries, we have deferred the following tables to future sprints:

* **`xp_predictions`** (Deferred to **Sprint 2**):
  - Stores outputs of prediction models.
* **`recommendations`** (Deferred to **Sprint 2**):
  - Stores output payloads of the ILP optimizer.
* **`recommendation_explanations`** (Deferred to **Sprint 3**):
  - Stores LLM-generated explanations for transfer/lineup/captaincy recommendations.
* **`news_items`** (Deferred to **Sprint 4**):
  - Stores scraped press-conference summaries and team injury updates for news scoring.
* **`backtest_runs`** (Deferred to **Sprint 2**):
  - Tracks simulation parameters and outcomes for evaluation against historical baseline scores.
* **`auto_submit_log`** (Deferred to **Sprint 5**):
  - Audits auto-submission transactions against the FPL write endpoints for safety and idempotency verification.
