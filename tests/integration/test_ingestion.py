from unittest.mock import patch, MagicMock
import pytest
from db.session import get_db_session
from db.models import Team, Player, Fixture, GameweekStat, UserSquad, UserTransferState, User, PlayerFeature, XpPrediction
from tasks.ingestion import run_fpl_ingestion
from ingestion.fpl_client import (
    BootstrapStaticResponse, FPLTeam, FPLPlayer, FPLFixture, FPLFixtureStat, FPLFixtureStatValue
)

# Mock data for integration test
mock_bootstrap = BootstrapStaticResponse(
    teams=[
        FPLTeam(id=1, name="Arsenal", short_name="ARS", code=11),
        FPLTeam(id=2, name="Chelsea", short_name="CHE", code=12)
    ],
    elements=[
        FPLPlayer(
            id=355, web_name="Saka", first_name="Bukayo", second_name="Saka",
            team=1, element_type=3, now_cost=85, status="a",
            chance_of_playing_next_round=100, chance_of_playing_this_round=100, news=None
        ),
        FPLPlayer(
            id=123, web_name="Palmer", first_name="Cole", second_name="Palmer",
            team=2, element_type=3, now_cost=75, status="a"
        )
    ]
)

mock_fixtures = [
    FPLFixture(
        id=1, event=1, team_h=1, team_a=2, team_h_difficulty=2, team_a_difficulty=3,
        kickoff_time="2026-08-11T19:00:00Z", finished=True,
        stats=[
            FPLFixtureStat(
                identifier="minutes",
                h=[FPLFixtureStatValue(value=90, element=355)],
                a=[FPLFixtureStatValue(value=90, element=123)]
            ),
            FPLFixtureStat(
                identifier="goals_scored",
                h=[FPLFixtureStatValue(value=1, element=355)],
                a=[]
            )
        ]
    )
]

@patch("tasks.ingestion.FPLClient")
def test_run_fpl_ingestion_integration(mock_client_class):
    # Setup mock client behavior
    mock_client = MagicMock()
    mock_client.get_bootstrap_static.return_value = mock_bootstrap
    mock_client.get_fixtures.return_value = mock_fixtures
    mock_client_class.return_value = mock_client
    
    # Clean database tables before run
    with get_db_session() as session:
        session.query(PlayerFeature).delete()
        session.query(XpPrediction).delete()
        session.query(UserSquad).delete()
        session.query(UserTransferState).delete()
        session.query(User).delete()
        session.query(GameweekStat).delete()
        session.query(Fixture).delete()
        session.query(Player).delete()
        session.query(Team).delete()
        session.commit()
        
    # Run first ingestion
    run_fpl_ingestion()
    
    # Assert database populated correctly
    with get_db_session() as session:
        # Check teams
        teams = session.query(Team).all()
        assert len(teams) == 2
        assert {t.short_name for t in teams} == {"ARS", "CHE"}
        
        # Check players
        players = session.query(Player).all()
        assert len(players) == 2
        saka = session.query(Player).filter_by(name="Saka").first()
        assert saka is not None
        assert saka.price == 85
        
        # Check fixtures
        fixtures = session.query(Fixture).all()
        assert len(fixtures) == 1
        assert fixtures[0].gameweek == 1
        
        # Check stats
        stats = session.query(GameweekStat).all()
        assert len(stats) == 2  # Saka and Palmer both have stats in the completed fixture
        saka_stat = session.query(GameweekStat).filter_by(player_id=saka.id, gameweek=1).first()
        assert saka_stat is not None
        assert saka_stat.minutes == 90
        assert saka_stat.goals == 1
        
    # Run second ingestion (Idempotency Check)
    run_fpl_ingestion()
    
    # Assert counts remain the same (no duplicates)
    with get_db_session() as session:
        assert session.query(Team).count() == 2
        assert session.query(Player).count() == 2
        assert session.query(Fixture).count() == 1
        assert session.query(GameweekStat).count() == 2
