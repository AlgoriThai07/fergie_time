"""
API contract tests for GET /recommendations/{user_id}/{gameweek}.

These tests use FastAPI's TestClient and mock out the database session,
the FPL client, and the optimizer calls.
"""
from unittest.mock import patch, MagicMock
import pytest
from fastapi.testclient import TestClient

from api.main import app
from db.models import User, Player, Team, UserSquad, UserTransferState, XpPrediction
from optimization.optimizer import PlayerData

client = TestClient(app)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_team(short_name="ARS"):
    t = MagicMock(spec=Team)
    t.id = 1
    t.short_name = short_name
    return t


def _make_player(id=1, fpl_id=355, name="Saka", position="MID", price=85, team_short="ARS"):
    p = MagicMock(spec=Player)
    p.id = id
    p.fpl_id = fpl_id
    p.name = name
    p.position = position
    p.price = price
    p.team = _make_team(team_short)
    p.team_id = 1
    return p


def _make_squad_entry(player, gameweek=1):
    e = MagicMock(spec=UserSquad)
    e.player = player
    e.gameweek = gameweek
    return e


def _make_prediction(player_id, gameweek=2, points=5.5):
    pred = MagicMock(spec=XpPrediction)
    pred.player_id = player_id
    pred.gameweek = gameweek
    pred.predicted_points = points
    pred.model_version = "baseline_v1"
    return pred


def _make_user(fpl_entry_id=12345, user_id=1):
    u = MagicMock(spec=User)
    u.id = user_id
    u.fpl_entry_id = fpl_entry_id
    return u


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@patch("api.recommendations.optimize_transfers")
@patch("api.recommendations.optimize_lineup")
@patch("api.recommendations.get_db_session")
def test_get_recommendations_success(mock_session_ctx, mock_lineup, mock_transfers):
    """Returns 200 with recommended lineup and transfer when data exists."""
    user = _make_user()

    # 15 players for the squad
    squad_players = [_make_player(id=i, name=f"Player_{i}", price=60) for i in range(1, 16)]
    squad_entries = [_make_squad_entry(p, gameweek=1) for p in squad_players]

    # xP predictions
    predictions = [_make_prediction(p.id, gameweek=2, points=6.0) for p in squad_players]

    # Additional target player for transfer
    target_player = _make_player(id=16, name="Salah", position="MID", price=125)
    predictions.append(_make_prediction(target_player.id, gameweek=2, points=9.5))

    # Transfer state (budget)
    transfer_state = MagicMock(spec=UserTransferState)
    transfer_state.bank_balance = 100  # £10.0m

    session = MagicMock()

    def mock_query(model):
        q = MagicMock()
        if model == User:
            q.filter_by.return_value.first.return_value = user
        elif model == UserSquad:
            q.filter_by.return_value.all.return_value = squad_entries
        elif model == XpPrediction:
            q.filter_by.return_value.all.return_value = predictions
        elif model == UserTransferState:
            q.filter_by.return_value.first.return_value = transfer_state
        elif model == Player:
            q.all.return_value = squad_players + [target_player]
        return q

    session.query.side_effect = mock_query
    mock_session_ctx.return_value.__enter__ = MagicMock(return_value=session)
    mock_session_ctx.return_value.__exit__ = MagicMock(return_value=False)

    # Map mock players to PlayerData to match actual optimizer return type
    squad_player_datas = [
        PlayerData(
            player_id=p.id,
            name=p.name,
            position=p.position,
            team_id=p.team_id,
            price=p.price,
        )
        for p in squad_players
    ]
    target_player_data = PlayerData(
        player_id=target_player.id,
        name=target_player.name,
        position=target_player.position,
        team_id=target_player.team_id,
        price=target_player.price,
    )

    # Mock optimizer returns
    mock_lineup.return_value = {
        "starting_xi": squad_player_datas[:11],
        "bench": squad_player_datas[11:],
        "formation": "1-4-4-2",
    }
    mock_transfers.return_value = {
        "transfers_in": [target_player_data],
        "transfers_out": [squad_player_datas[0]],
        "new_squad": squad_player_datas[1:] + [target_player_data],
    }

    resp = client.get("/recommendations/12345/2")
    assert resp.status_code == 200

    body = resp.json()
    assert body["user_id"] == user.id
    assert body["gameweek"] == 2

    # Verify Lineup structure
    assert "lineup" in body
    assert len(body["lineup"]["starting_xi"]) == 11
    assert len(body["lineup"]["bench"]) == 4
    assert body["lineup"]["formation"] == "1-4-4-2"

    # Verify Transfer structure
    assert "transfer" in body
    assert body["transfer"] is not None
    assert body["transfer"]["transfer_in"]["name"] == "Salah"
    assert body["transfer"]["transfer_out"]["name"] == "Player_1"
    assert "xp_gain" in body["transfer"]

    # Verify underlying xP map
    assert "xp_map" in body
    assert str(target_player.id) in body["xp_map"]
    assert str(squad_players[0].id) in body["xp_map"]


@patch("api.recommendations.get_db_session")
def test_get_recommendations_missing_predictions(mock_session_ctx):
    """Returns 409 Conflict when predictions are missing for the gameweek."""
    user = _make_user()
    squad_players = [_make_player(id=i) for i in range(1, 16)]
    squad_entries = [_make_squad_entry(p, gameweek=1) for p in squad_players]

    session = MagicMock()

    def mock_query(model):
        q = MagicMock()
        if model == User:
            q.filter_by.return_value.first.return_value = user
        elif model == UserSquad:
            q.filter_by.return_value.all.return_value = squad_entries
        elif model == XpPrediction:
            # Missing predictions
            q.filter_by.return_value.all.return_value = []
        return q

    session.query.side_effect = mock_query
    mock_session_ctx.return_value.__enter__ = MagicMock(return_value=session)
    mock_session_ctx.return_value.__exit__ = MagicMock(return_value=False)

    resp = client.get("/recommendations/12345/2")
    assert resp.status_code == 409
    assert "xP predictions are missing" in resp.json()["detail"]


@patch("api.recommendations._fetch_and_persist_squad")
@patch("api.recommendations.get_db_session")
def test_get_recommendations_missing_squad_live_fetch_fails(mock_session_ctx, mock_fetch):
    """Returns 503 Service Unavailable when user squad is missing and live fetch raises exception."""
    mock_fetch.side_effect = Exception("FPL API error")

    session = MagicMock()
    # Mocking User query returning None and UserSquad returning empty list
    session.query.return_value.filter_by.return_value.first.return_value = None
    session.query.return_value.filter_by.return_value.all.return_value = []

    mock_session_ctx.return_value.__enter__ = MagicMock(return_value=session)
    mock_session_ctx.return_value.__exit__ = MagicMock(return_value=False)

    resp = client.get("/recommendations/12345/2")
    assert resp.status_code == 503
    assert "live FPL fetch failed" in resp.json()["detail"]
