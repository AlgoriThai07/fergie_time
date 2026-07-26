import pytest
from db.models import Team, Player, Fixture, GameweekStat, PlayerFeature
from db.session import get_db_session
from tasks.features import compute_player_features


@pytest.fixture(autouse=True)
def clean_db():
    """Clean the database before and after each test."""
    with get_db_session() as session:
        session.query(PlayerFeature).delete()
        session.query(GameweekStat).delete()
        session.query(Fixture).delete()
        session.query(Player).delete()
        session.query(Team).delete()
        session.commit()
    yield
    with get_db_session() as session:
        session.query(PlayerFeature).delete()
        session.query(GameweekStat).delete()
        session.query(Fixture).delete()
        session.query(Player).delete()
        session.query(Team).delete()
        session.commit()


def test_compute_player_features_success():
    with get_db_session() as session:
        # 1. Create Teams
        t_a = Team(fpl_id=1, name="Arsenal", short_name="ARS")
        t_b = Team(fpl_id=2, name="Chelsea", short_name="CHE")
        t_c = Team(fpl_id=3, name="Liverpool", short_name="LIV")
        t_d = Team(fpl_id=4, name="Everton", short_name="EVE")
        session.add_all([t_a, t_b, t_c, t_d])
        session.flush()

        # 2. Create Players
        # Saka (Team A): standard 5+ historical gameweeks
        saka = Player(fpl_id=101, name="Saka", first_name="Bukayo", second_name="Saka", team_id=t_a.id, position="MID", price=85, status="a")
        # Cole (Team B): fewer than 5 historical gameweeks (2 games)
        cole = Player(fpl_id=102, name="Palmer", first_name="Cole", second_name="Palmer", team_id=t_b.id, position="MID", price=75, status="a")
        # Newguy (Team C): no historical gameweeks
        newguy = Player(fpl_id=103, name="Newguy", first_name="New", second_name="Guy", team_id=t_c.id, position="FWD", price=55, status="a")
        # Salah (Team D): blank gameweek upcoming (no fixtures in GW 6)
        salah = Player(fpl_id=104, name="Salah", first_name="Mohamed", second_name="Salah", team_id=t_d.id, position="MID", price=125, status="a")
        session.add_all([saka, cole, newguy, salah])
        session.flush()

        # 3. Create historical GameweekStats (GW 1-5)
        # Saka stats
        saka_stats = [
            GameweekStat(player_id=saka.id, gameweek=1, minutes=90, total_points=2),
            GameweekStat(player_id=saka.id, gameweek=2, minutes=90, total_points=3),
            GameweekStat(player_id=saka.id, gameweek=3, minutes=90, total_points=5),
            GameweekStat(player_id=saka.id, gameweek=4, minutes=90, total_points=1),
            GameweekStat(player_id=saka.id, gameweek=5, minutes=90, total_points=4),
        ]
        # Cole stats (only played GW 4 and 5)
        cole_stats = [
            GameweekStat(player_id=cole.id, gameweek=4, minutes=90, total_points=6),
            GameweekStat(player_id=cole.id, gameweek=5, minutes=45, total_points=2),
        ]
        # Salah stats
        salah_stats = [
            GameweekStat(player_id=salah.id, gameweek=5, minutes=90, total_points=10),
        ]
        session.add_all(saka_stats + cole_stats + salah_stats)

        # 4. Create fixtures for GW 6 (target gameweek)
        # Fixture 1: ARS (Home) vs CHE (Away). ARS difficulty=2, CHE difficulty=4
        f1 = Fixture(fpl_id=201, gameweek=6, home_team_id=t_a.id, away_team_id=t_b.id, difficulty_home=2, difficulty_away=4, kickoff_time="2026-08-25T15:00:00Z", status="upcoming")
        # Fixture 2 (Double GW for LIV and CHE): LIV (Home) vs CHE (Away). LIV difficulty=3, CHE difficulty=5
        f2 = Fixture(fpl_id=202, gameweek=6, home_team_id=t_c.id, away_team_id=t_b.id, difficulty_home=3, difficulty_away=5, kickoff_time="2026-08-28T15:00:00Z", status="upcoming")
        session.add_all([f1, f2])
        session.flush()

        saka_id = saka.id
        cole_id = cole.id
        newguy_id = newguy.id
        salah_id = salah.id

        session.commit()

    # 5. Run the Celery task for gameweek 6
    compute_player_features(gameweek=6)

    # 6. Verify results
    with get_db_session() as session:
        features = session.query(PlayerFeature).filter_by(gameweek=6).all()
        assert len(features) == 4

        saka_feat = session.query(PlayerFeature).filter_by(player_id=saka_id, gameweek=6).first()
        assert saka_feat is not None
        # Saka expected points rolling avg: (2+3+5+1+4)/5 = 3.0
        assert saka_feat.rolling_avg_points == pytest.approx(3.0)
        assert saka_feat.minutes_trend == pytest.approx(90.0)
        # Saka's team ARS has home fixture vs CHE (difficulty_home=2)
        assert saka_feat.upcoming_fixture_difficulty == pytest.approx(2.0)

        cole_feat = session.query(PlayerFeature).filter_by(player_id=cole_id, gameweek=6).first()
        assert cole_feat is not None
        # Cole expected points rolling avg: (6+2)/2 = 4.0
        assert cole_feat.rolling_avg_points == pytest.approx(4.0)
        assert cole_feat.minutes_trend == pytest.approx(67.5)
        # Cole's team CHE has double GW: away vs ARS (difficulty_away=4) and away vs LIV (difficulty_away=5)
        # Average FDR: (4+5)/2 = 4.5
        assert cole_feat.upcoming_fixture_difficulty == pytest.approx(4.5)

        newguy_feat = session.query(PlayerFeature).filter_by(player_id=newguy_id, gameweek=6).first()
        assert newguy_feat is not None
        # Newguy expected points rolling avg (no history): 0.0
        assert newguy_feat.rolling_avg_points == pytest.approx(0.0)
        assert newguy_feat.minutes_trend == pytest.approx(0.0)
        # Newguy's team LIV has home fixture vs CHE (difficulty_home=3)
        assert newguy_feat.upcoming_fixture_difficulty == pytest.approx(3.0)

        salah_feat = session.query(PlayerFeature).filter_by(player_id=salah_id, gameweek=6).first()
        assert salah_feat is not None
        # Salah expected points rolling avg (1 game): 10.0
        assert salah_feat.rolling_avg_points == pytest.approx(10.0)
        assert salah_feat.minutes_trend == pytest.approx(90.0)
        # Salah's team EVE has no fixtures in GW 6 (blank gameweek)
        assert salah_feat.upcoming_fixture_difficulty is None


def test_compute_player_features_idempotent():
    with get_db_session() as session:
        t_a = Team(fpl_id=1, name="Arsenal", short_name="ARS")
        session.add(t_a)
        session.flush()

        saka = Player(fpl_id=101, name="Saka", first_name="Bukayo", second_name="Saka", team_id=t_a.id, position="MID", price=85, status="a")
        session.add(saka)
        session.flush()

        # GW 5 stat
        s1 = GameweekStat(player_id=saka.id, gameweek=5, minutes=90, total_points=5)
        session.add(s1)

        # GW 6 fixture
        f1 = Fixture(fpl_id=201, gameweek=6, home_team_id=t_a.id, away_team_id=t_a.id, difficulty_home=2, difficulty_away=2, kickoff_time="2026-08-25T15:00:00Z", status="upcoming")
        session.add(f1)
        session.flush()
        saka_id = saka.id
        session.commit()

    # Run first time
    compute_player_features(gameweek=6)

    with get_db_session() as session:
        feat1 = session.query(PlayerFeature).filter_by(player_id=saka_id, gameweek=6).first()
        assert feat1 is not None
        assert feat1.rolling_avg_points == 5.0
        assert feat1.upcoming_fixture_difficulty == 2.0

    # Add more stats and run second time to verify updates
    with get_db_session() as session:
        # Update GW 5 stat points to 10
        s1_db = session.query(GameweekStat).filter_by(player_id=saka_id, gameweek=5).first()
        s1_db.total_points = 10
        # Update fixture difficulty to 4
        f1_db = session.query(Fixture).filter_by(fpl_id=201).first()
        f1_db.difficulty_home = 4
        session.commit()

    # Run second time
    compute_player_features(gameweek=6)

    with get_db_session() as session:
        # Check there is still only one record for (player_id, gameweek)
        count = session.query(PlayerFeature).filter_by(player_id=saka_id, gameweek=6).count()
        assert count == 1

        feat2 = session.query(PlayerFeature).filter_by(player_id=saka_id, gameweek=6).first()
        assert feat2.rolling_avg_points == 10.0
        assert feat2.upcoming_fixture_difficulty == 4.0
