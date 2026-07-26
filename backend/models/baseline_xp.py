"""
Baseline xP model for FPL player point prediction.

Formula:
    predicted_points = rolling_avg_points * fixture_difficulty_multiplier

Fixture difficulty multiplier:
    FDR 1 → 1.30  (easiest fixture)
    FDR 2 → 1.15
    FDR 3 → 1.00  (neutral)
    FDR 4 → 0.85
    FDR 5 → 0.70  (hardest fixture)

Confidence formula (placeholder for Sprint 6 ML confidence intervals):
    confidence = min(games_in_window, MAX_WINDOW) / MAX_WINDOW
    where MAX_WINDOW = 5 (the rolling-average window size)

    Rationale: a player with 5 gameweeks of history has full confidence (1.0),
    a player with 2 gameweeks has confidence 0.4, and a brand-new signing with
    0 historical gameweeks has confidence 0.0.  This is intentionally simple
    and transparent so that the improvement from real prediction-interval-based
    confidence (Sprint 6) can be measured directly against this baseline.

Interface contract (CLAUDE.md / fpl-agent-plan.md §C):
    predict(player_id, gameweek) -> (point_estimate: float, confidence: float)

    This interface is stable. The ML model (Sprint 6) will implement the same
    signature so the optimizer and API layer never need to change.
"""

from __future__ import annotations

import logging

from db.models import GameweekStat, PlayerFeature
from db.session import get_db_session

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MODEL_VERSION = "baseline_v1"
MAX_WINDOW = 5  # rolling average window size

# FDR → multiplier lookup.  FDR outside [1-5] falls back to 1.0 (neutral).
_FDR_MULTIPLIER: dict[int, float] = {
    1: 1.30,
    2: 1.15,
    3: 1.00,
    4: 0.85,
    5: 0.70,
}


def _fdr_multiplier(fdr: float | None) -> float:
    """Return the fixture-difficulty multiplier for a given FDR value.

    FDR is stored as a float average (e.g. 4.5 for a double gameweek), so
    we round to the nearest integer before looking up.  If fdr is None
    (blank gameweek), the player's expected points default to 0.
    """
    if fdr is None:
        return 0.0
    rounded = round(fdr)
    return _FDR_MULTIPLIER.get(rounded, 1.0)


def predict(player_id: int, gameweek: int) -> tuple[float, float]:
    """Return (point_estimate, confidence) for *player_id* in *gameweek*.

    Reads from the player_features table which must have been populated by
    tasks.features.compute_player_features before this is called.

    Returns (0.0, 0.0) and logs a warning if no features row exists, rather
    than raising — the optimizer should treat missing predictions as 0 xP
    and surface a "data may be stale" warning to the user.
    """
    with get_db_session() as session:
        feature = (
            session.query(PlayerFeature)
            .filter_by(player_id=player_id, gameweek=gameweek)
            .first()
        )
        if feature is None:
            logger.warning(
                "No player_features row for player_id=%s gameweek=%s; "
                "returning (0.0, 0.0).  Run compute_player_features first.",
                player_id,
                gameweek,
            )
            return 0.0, 0.0

        rolling_avg = feature.rolling_avg_points or 0.0
        fdr = feature.upcoming_fixture_difficulty

        # Count how many historical gameweeks fed into this rolling average
        # so we can derive confidence.
        games_in_window = (
            session.query(GameweekStat)
            .filter(
                GameweekStat.player_id == player_id,
                GameweekStat.gameweek < gameweek,
            )
            .count()
        )
        # Cap at MAX_WINDOW — we only used the last 5 games for the average
        games_in_window = min(games_in_window, MAX_WINDOW)

        point_estimate = rolling_avg * _fdr_multiplier(fdr)

        # Confidence: fraction of the maximum window that is filled.
        # 0.0 = no history (new signing), 1.0 = full 5-game window.
        confidence = games_in_window / MAX_WINDOW

        return point_estimate, confidence
