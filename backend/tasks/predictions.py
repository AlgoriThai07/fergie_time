"""
Celery task: run the baseline xP model for all players for the upcoming gameweek
and write results into xp_predictions.

Idempotency: the unique constraint on (player_id, gameweek, model_version)
ensures that re-running for the same gameweek overwrites the existing row
rather than inserting a duplicate.
"""
import logging

from db.models import Fixture, GameweekStat, Player, XpPrediction
from db.session import get_db_session
from models.baseline_xp import MODEL_VERSION, predict
from tasks.celery_app import app

logger = logging.getLogger(__name__)


@app.task(name="tasks.predictions.run_baseline_xp_predictions")
def run_baseline_xp_predictions(gameweek: int = None):
    """
    Runs the baseline xP model for all players and upserts into xp_predictions.
    If *gameweek* is not provided, resolves the upcoming gameweek automatically.
    """
    with get_db_session() as session:
        # Resolve gameweek (mirrors the logic in tasks.features)
        if gameweek is None:
            upcoming_gw = (
                session.query(Fixture.gameweek)
                .filter(Fixture.status == "upcoming")
                .order_by(Fixture.gameweek.asc())
                .first()
            )
            if upcoming_gw:
                gameweek = upcoming_gw[0]
            else:
                max_stat_gw = (
                    session.query(GameweekStat.gameweek)
                    .order_by(GameweekStat.gameweek.desc())
                    .first()
                )
                gameweek = max_stat_gw[0] + 1 if max_stat_gw else 1

        logger.info(
            "Running baseline xP predictions for gameweek %s (model_version=%s)",
            gameweek,
            MODEL_VERSION,
        )

        players = session.query(Player).all()

    # Call predict() outside the session so it opens its own session per call.
    # This keeps session lifetimes short and avoids expiry issues.
    written = 0
    for player in players:
        point_estimate, confidence = predict(player.id, gameweek)

        with get_db_session() as session:
            prediction = (
                session.query(XpPrediction)
                .filter_by(
                    player_id=player.id,
                    gameweek=gameweek,
                    model_version=MODEL_VERSION,
                )
                .first()
            )
            if prediction is None:
                prediction = XpPrediction(
                    player_id=player.id,
                    gameweek=gameweek,
                    model_version=MODEL_VERSION,
                )
                session.add(prediction)

            prediction.predicted_points = point_estimate
            prediction.confidence = confidence
            session.commit()
        written += 1

    logger.info(
        "Wrote %d xP predictions for gameweek %s (model_version=%s)",
        written,
        gameweek,
        MODEL_VERSION,
    )
