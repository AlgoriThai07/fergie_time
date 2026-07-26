import logging

from db.models import Fixture, GameweekStat, Player, Team
from db.session import get_db_session
from ingestion.fpl_client import FPLClient
from tasks.celery_app import app

logger = logging.getLogger(__name__)

POSITION_MAP = {1: "GKP", 2: "DEF", 3: "MID", 4: "FWD"}


@app.task
def run_fpl_ingestion():
    """Celery task to ingest bootstrap-static and fixtures data from the FPL API."""
    logger.info("Starting FPL data ingestion...")
    client = FPLClient()

    try:
        bootstrap_data = client.get_bootstrap_static()
        fixtures_data = client.get_fixtures()
    except Exception as e:
        logger.error(f"Failed to fetch data from FPL API: {e}")
        raise

    with get_db_session() as session:
        # 1. Ingest Teams
        team_id_map = {}  # Map FPL team_id -> Database team.id
        for raw_team in bootstrap_data.teams:
            try:
                # Validation
                if not raw_team.id or not raw_team.name or not raw_team.short_name:
                    raise ValueError("Missing required fields in team data")

                db_team = session.query(Team).filter_by(fpl_id=raw_team.id).first()
                if not db_team:
                    db_team = Team(fpl_id=raw_team.id)
                    session.add(db_team)

                db_team.name = raw_team.name
                db_team.short_name = raw_team.short_name
                session.flush()  # Populates db_team.id
                team_id_map[raw_team.id] = db_team.id
            except Exception as e:
                team_id = raw_team.id if hasattr(raw_team, "id") else "unknown"
                logger.error(f"Failed to ingest team {team_id}: {e}")

        # 2. Ingest Players
        player_id_map = {}  # Map FPL player_id -> Database player.id
        for raw_player in bootstrap_data.elements:
            try:
                # Validation
                if not raw_player.id or not raw_player.web_name or not raw_player.team:
                    raise ValueError("Missing required fields in player data")

                db_team_id = team_id_map.get(raw_player.team)
                if not db_team_id:
                    raise ValueError(
                        f"Team FPL ID {raw_player.team} not found in database"
                    )

                db_player = (
                    session.query(Player).filter_by(fpl_id=raw_player.id).first()
                )
                if not db_player:
                    db_player = Player(fpl_id=raw_player.id)
                    session.add(db_player)

                db_player.name = raw_player.web_name
                db_player.first_name = raw_player.first_name
                db_player.second_name = raw_player.second_name
                db_player.team_id = db_team_id
                db_player.position = POSITION_MAP.get(raw_player.element_type, "MID")
                db_player.price = raw_player.now_cost
                db_player.status = raw_player.status
                db_player.chance_of_playing_next_round = (
                    raw_player.chance_of_playing_next_round
                )
                db_player.chance_of_playing_this_round = (
                    raw_player.chance_of_playing_this_round
                )
                db_player.news = raw_player.news
                session.flush()
                player_id_map[raw_player.id] = db_player.id
            except Exception as e:
                player_id = raw_player.id if hasattr(raw_player, "id") else "unknown"
                logger.error(f"Failed to ingest player {player_id}: {e}")

        # 3. Ingest Fixtures
        for raw_fixture in fixtures_data:
            try:
                # Validation
                if (
                    not raw_fixture.id
                    or not raw_fixture.team_h
                    or not raw_fixture.team_a
                    or raw_fixture.event is None
                ):
                    raise ValueError("Missing required fields in fixture data")

                db_home_team_id = team_id_map.get(raw_fixture.team_h)
                db_away_team_id = team_id_map.get(raw_fixture.team_a)
                if not db_home_team_id or not db_away_team_id:
                    raise ValueError(
                        f"Home/Away team FPL IDs ({raw_fixture.team_h}/"
                        f"{raw_fixture.team_a}) not found in database"
                    )

                db_fixture = (
                    session.query(Fixture).filter_by(fpl_id=raw_fixture.id).first()
                )
                if not db_fixture:
                    db_fixture = Fixture(fpl_id=raw_fixture.id)
                    session.add(db_fixture)

                db_fixture.gameweek = raw_fixture.event
                db_fixture.home_team_id = db_home_team_id
                db_fixture.away_team_id = db_away_team_id
                db_fixture.difficulty_home = raw_fixture.team_h_difficulty
                db_fixture.difficulty_away = raw_fixture.team_a_difficulty
                db_fixture.kickoff_time = raw_fixture.kickoff_time
                db_fixture.status = "finished" if raw_fixture.finished else "upcoming"
                session.flush()

                # 4. Ingest Gameweek Stats (from completed fixtures)
                if raw_fixture.finished:
                    fixture_player_stats = {}  # element_fpl_id -> dict of stats

                    for stat_category in raw_fixture.stats:
                        identifier = stat_category.identifier
                        field_map = {
                            "minutes": "minutes",
                            "goals_scored": "goals",
                            "assists": "assists",
                            "bonus": "bonus",
                        }

                        db_field = field_map.get(identifier)
                        if not db_field:
                            continue

                        # Parse home stats
                        for val in stat_category.h:
                            fixture_player_stats.setdefault(val.element, {})[
                                db_field
                            ] = val.value
                        # Parse away stats
                        for val in stat_category.a:
                            fixture_player_stats.setdefault(val.element, {})[
                                db_field
                            ] = val.value

                    # Upsert gameweek stats for involved players
                    for player_fpl_id, stats in fixture_player_stats.items():
                        db_player_id = player_id_map.get(player_fpl_id)
                        if not db_player_id:
                            continue

                        db_gw_stat = (
                            session.query(GameweekStat)
                            .filter_by(
                                player_id=db_player_id, gameweek=raw_fixture.event
                            )
                            .first()
                        )

                        if not db_gw_stat:
                            db_gw_stat = GameweekStat(
                                player_id=db_player_id, gameweek=raw_fixture.event
                            )
                            session.add(db_gw_stat)

                        db_gw_stat.minutes = stats.get("minutes", 0)
                        db_gw_stat.goals = stats.get("goals", 0)
                        db_gw_stat.assists = stats.get("assists", 0)
                        db_gw_stat.bonus = stats.get("bonus", 0)
                        db_gw_stat.total_points = (
                            stats.get("goals", 0) * 4
                            + stats.get("assists", 0) * 3
                            + stats.get("bonus", 0)
                        )  # Simplified calculation for fallback
                        session.flush()

            except Exception as e:
                fixture_id = raw_fixture.id if hasattr(raw_fixture, "id") else "unknown"
                logger.error(f"Failed to ingest fixture {fixture_id}: {e}")

    logger.info("FPL data ingestion completed.")
