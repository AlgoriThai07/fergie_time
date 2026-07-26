from __future__ import annotations

import logging

from db.models import Fixture, GameweekStat, Player, PlayerFeature
from db.session import get_db_session
from tasks.celery_app import app

logger = logging.getLogger(__name__)


@app.task(name="tasks.features.compute_player_features")
def compute_player_features(gameweek: int | None = None):
    """
    Computes rolling averages and upcoming fixture difficulties for all players,
    and updates or inserts the results into player_features for the given gameweek.
    If no gameweek is specified, it determines the upcoming gameweek automatically.
    """
    with get_db_session() as session:
        # 1. Resolve gameweek if not provided
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

        logger.info(f"Computing player features for gameweek {gameweek}")

        players = session.query(Player).all()

        for player in players:
            # 2. Compute rolling stats from completed gameweeks before target gameweek
            history = (
                session.query(GameweekStat)
                .filter(
                    GameweekStat.player_id == player.id,
                    GameweekStat.gameweek < gameweek,
                )
                .order_by(GameweekStat.gameweek.desc())
                .limit(5)
                .all()
            )

            if history:
                rolling_avg_points = sum(h.total_points for h in history) / len(history)
                minutes_trend = sum(h.minutes for h in history) / len(history)
            else:
                rolling_avg_points = 0.0
                minutes_trend = 0.0

            # 3. Compute upcoming fixture difficulty
            fixtures = (
                session.query(Fixture)
                .filter(
                    Fixture.gameweek == gameweek,
                    (Fixture.home_team_id == player.team_id)
                    | (Fixture.away_team_id == player.team_id),
                )
                .all()
            )

            if fixtures:
                difficulties = [
                    f.difficulty_home
                    if f.home_team_id == player.team_id
                    else f.difficulty_away
                    for f in fixtures
                ]
                upcoming_fixture_difficulty = sum(difficulties) / len(difficulties)
            else:
                upcoming_fixture_difficulty = None

            # 4. Upsert into player_features
            feature = (
                session.query(PlayerFeature)
                .filter_by(player_id=player.id, gameweek=gameweek)
                .first()
            )
            if not feature:
                feature = PlayerFeature(player_id=player.id, gameweek=gameweek)
                session.add(feature)

            feature.rolling_avg_points = rolling_avg_points
            feature.minutes_trend = minutes_trend
            feature.upcoming_fixture_difficulty = upcoming_fixture_difficulty

        session.commit()
        logger.info(
            "Successfully computed features for %d players in gameweek %s",
            len(players),
            gameweek,
        )
