"""
API contract tests for GET /squad/{user_id}.

These tests use FastAPI's TestClient and mock out both the database session
and the FPL client, so they run without a live DB or network.
"""
from unittest.mock import patch, MagicMock
import pytest
from fastapi.testclient import TestClient

from api.main import app
from api.squad import SquadResponse, SquadPlayerResponse
from db.models import User, Player, Team, UserSquad

client = TestClient(app)


# ---------------------------------------------------------------------------
# Helpers: factory functions for mock ORM objects
# ---------------------------------------------------------------------------

def _make_team(short_name="ARS"):
    t = MagicMock(spec=Team)
    t.short_name = short_name
    return t

def _make_player(fpl_id=355, name="Saka", first_name="Bukayo", second_name="Saka",
                  position="MID", price=85, team_short="ARS"):
    p = MagicMock(spec=Player)
    p.id = 1
    p.fpl_id = fpl_id
    p.name = name
    p.first_name = first_name
    p.second_name = second_name
    p.position = position
    p.price = price
    p.team = _make_team(team_short)
    return p

def _make_squad_entry(player, gameweek=1, is_starting=True, is_captain=False, is_vice=False):
    e = MagicMock(spec=UserSquad)
    e.player = player
    e.gameweek = gameweek
    e.is_starting = is_starting
    e.is_captain = is_captain
    e.is_vice = is_vice
    return e

def _make_user(fpl_entry_id=12345, user_id=1):
    u = MagicMock(spec=User)
    u.id = user_id
    u.fpl_entry_id = fpl_entry_id
    return u


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@patch("api.squad._get_current_gameweek", return_value=1)
@patch("api.squad.get_db_session")
def test_get_squad_from_db(mock_session_ctx, mock_gw):
    """Returns 200 with correct shape when squad is already in the database."""
    user = _make_user()
    player = _make_player()
    entry = _make_squad_entry(player, is_captain=True)

    session = MagicMock()
    session.query.return_value.filter_by.return_value.first.return_value = user
    session.query.return_value.filter_by.return_value.all.return_value = [entry]
    mock_session_ctx.return_value.__enter__ = MagicMock(return_value=session)
    mock_session_ctx.return_value.__exit__ = MagicMock(return_value=False)

    resp = client.get("/squad/12345")
    assert resp.status_code == 200

    body = resp.json()
    # Top-level shape
    assert "user_id" in body
    assert "fpl_entry_id" in body
    assert "gameweek" in body
    assert "squad" in body
    assert isinstance(body["squad"], list)

    # Player shape
    p = body["squad"][0]
    for field in ("player_id", "fpl_id", "name", "first_name", "second_name",
                  "team", "position", "price", "is_starting", "is_captain", "is_vice"):
        assert field in p, f"Missing field '{field}' in player response"

    # Values
    assert p["name"] == "Saka"
    assert p["position"] == "MID"
    assert p["price"] == 85
    assert p["is_captain"] is True


@patch("api.squad._get_current_gameweek", return_value=1)
@patch("api.squad._fetch_and_persist_squad")
@patch("api.squad.get_db_session")
def test_get_squad_live_fallback(mock_session_ctx, mock_fetch, mock_gw):
    """Falls back to live FPL fetch when no squad rows exist, then returns them."""
    user = _make_user()
    player = _make_player()
    entry = _make_squad_entry(player)

    def filter_by_side_effect(**kwargs):
        result = MagicMock()
        if "fpl_entry_id" in kwargs:
            result.first.return_value = None   # user not in DB
        elif "user_id" in kwargs:
            # After live fetch the squad should be populated; always return entries
            result.all.return_value = [entry]
        return result

    session = MagicMock()
    session.query.return_value.filter_by.side_effect = filter_by_side_effect

    mock_fetch.return_value = user
    mock_session_ctx.return_value.__enter__ = MagicMock(return_value=session)
    mock_session_ctx.return_value.__exit__ = MagicMock(return_value=False)

    resp = client.get("/squad/12345")
    assert resp.status_code == 200
    mock_fetch.assert_called_once_with(12345, 1, session)


@patch("api.squad._get_current_gameweek", return_value=1)
@patch("api.squad._fetch_and_persist_squad", side_effect=Exception("FPL API down"))
@patch("api.squad.get_db_session")
def test_get_squad_live_fallback_failure(mock_session_ctx, mock_fetch, mock_gw):
    """Returns 503 when squad is missing from DB and live FPL fetch fails."""
    session = MagicMock()
    call = MagicMock()
    call.first.return_value = None
    call.all.return_value = []
    session.query.return_value.filter_by.return_value = call
    mock_session_ctx.return_value.__enter__ = MagicMock(return_value=session)
    mock_session_ctx.return_value.__exit__ = MagicMock(return_value=False)

    resp = client.get("/squad/99999")
    assert resp.status_code == 503
    assert "FPL fetch failed" in resp.json()["detail"]


@patch("api.squad._get_current_gameweek", return_value=1)
@patch("api.squad.get_db_session")
def test_get_squad_pydantic_schema(mock_session_ctx, mock_gw):
    """Validates the full response parses cleanly into SquadResponse."""
    user = _make_user()
    player = _make_player()
    entry = _make_squad_entry(player)

    session = MagicMock()
    session.query.return_value.filter_by.return_value.first.return_value = user
    session.query.return_value.filter_by.return_value.all.return_value = [entry]
    mock_session_ctx.return_value.__enter__ = MagicMock(return_value=session)
    mock_session_ctx.return_value.__exit__ = MagicMock(return_value=False)

    resp = client.get("/squad/12345")
    assert resp.status_code == 200

    # Should parse without error
    parsed = SquadResponse.model_validate(resp.json())
    assert len(parsed.squad) == 1
    assert isinstance(parsed.squad[0], SquadPlayerResponse)

