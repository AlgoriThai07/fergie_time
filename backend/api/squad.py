"""
GET /squad/{user_id}

Returns the user's current squad (15 players) with team, position, price,
and starting/bench/captain status.

If no squad is found in user_squads for the user, fetches it live from the
FPL API via get_entry_picks(), persists it, then returns it.
"""

import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from db.models import Player, Team, User, UserSquad, UserTransferState
from db.session import get_db_session
from ingestion.fpl_client import FPLClient

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/squad", tags=["squad"])


# ---------------------------------------------------------------------------
# Response Schema
# ---------------------------------------------------------------------------


class SquadPlayerResponse(BaseModel):
    """A single player entry in the squad response."""

    player_id: int  # Internal DB id
    fpl_id: int  # FPL element id
    name: str  # web_name (e.g. "Saka")
    first_name: str
    second_name: str
    team: str  # Short name, e.g. "ARS"
    position: str  # "GKP", "DEF", "MID", or "FWD"
    price: int  # Tenths of a million, e.g. 85 = £8.5m
    is_starting: bool
    is_captain: bool
    is_vice: bool


class SquadResponse(BaseModel):
    """Top-level squad response."""

    user_id: int  # Internal DB user id
    fpl_entry_id: int  # FPL manager entry id
    gameweek: int
    squad: list[SquadPlayerResponse]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_current_gameweek(client: FPLClient) -> int:
    """
    Determine the current gameweek from bootstrap-static's events list.
    Returns the first event that is 'current', or the highest 'finished' gw as fallback.
    """
    # bootstrap-static returns an 'events' key with all GW metadata;
    # FPLPlayer is the element model, so we call the underlying HTTP
    # client directly here to access the raw 'events' list.
    url = f"{client.BASE_URL}/bootstrap-static/"
    resp = client.client.get(url)
    events = resp.json().get("events", [])
    for event in events:
        if event.get("is_current"):
            return event["id"]
    # Fallback: last finished gw
    finished = [e["id"] for e in events if e.get("finished")]
    if finished:
        return max(finished)
    return 1  # pre-season default


def _fetch_and_persist_squad(
    fpl_entry_id: int,
    gameweek: int,
    session,
) -> User:
    """
    Fetch picks from FPL API for the given entry/gameweek, upsert the User row,
    and upsert UserSquad rows. Returns the User ORM object.
    """
    client = FPLClient()

    # Upsert User
    user = session.query(User).filter_by(fpl_entry_id=fpl_entry_id).first()
    if not user:
        user = User(fpl_entry_id=fpl_entry_id)
        session.add(user)
        session.flush()

    picks_resp = client.get_entry_picks(fpl_entry_id, gameweek)

    # Persist transfer state (bank balance) if present in history
    if picks_resp.entry_history:
        transfer_state = (
            session.query(UserTransferState)
            .filter_by(user_id=user.id, gameweek=gameweek)
            .first()
        )
        if not transfer_state:
            transfer_state = UserTransferState(
                user_id=user.id,
                gameweek=gameweek,
            )
            session.add(transfer_state)
        transfer_state.bank_balance = picks_resp.entry_history.bank

    for pick in picks_resp.picks:
        player = session.query(Player).filter_by(fpl_id=pick.element).first()
        if not player:
            # Player not yet ingested — skip with a warning; full ingestion task
            # will populate players later.
            logger.warning(
                "Player fpl_id=%d not found in DB during live squad fetch; skipping.",
                pick.element,
            )
            continue

        # Position 1-11 = starting, 12-15 = bench
        is_starting = pick.position <= 11

        squad_entry = (
            session.query(UserSquad)
            .filter_by(user_id=user.id, gameweek=gameweek, player_id=player.id)
            .first()
        )
        if not squad_entry:
            squad_entry = UserSquad(
                user_id=user.id,
                gameweek=gameweek,
                player_id=player.id,
            )
            session.add(squad_entry)

        squad_entry.is_starting = is_starting
        squad_entry.is_captain = pick.is_captain
        squad_entry.is_vice = pick.is_vice

    session.flush()
    return user


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------


@router.get("/{user_id}", response_model=SquadResponse)
def get_squad(user_id: int):
    """
    Return the current squad for an FPL entry id.

    - If the user and their squad exist in user_squads, returns the persisted data.
    - If not, fetches live from the FPL API, persists it, and returns it.
    """
    with get_db_session() as session:
        user = session.query(User).filter_by(fpl_entry_id=user_id).first()

        # Determine current gameweek (needed for both DB lookup and live fetch)
        client = FPLClient()
        gameweek = _get_current_gameweek(client)

        if user:
            squad_entries = (
                session.query(UserSquad)
                .filter_by(user_id=user.id, gameweek=gameweek)
                .all()
            )
        else:
            squad_entries = []

        # Fallback: live fetch + persist if no rows in DB
        if not squad_entries:
            try:
                user = _fetch_and_persist_squad(user_id, gameweek, session)
                squad_entries = (
                    session.query(UserSquad)
                    .filter_by(user_id=user.id, gameweek=gameweek)
                    .all()
                )
            except Exception as exc:
                logger.error(
                    "Live squad fetch failed for fpl_entry_id=%d: %s", user_id, exc
                )
                raise HTTPException(
                    status_code=503,
                    detail="Squad not found in database and live FPL fetch failed.",
                ) from exc

        if not squad_entries:
            raise HTTPException(
                status_code=404,
                detail=(
                    f"No squad found for FPL entry id {user_id} in gameweek {gameweek}."
                ),
            )

        squad_players = []
        for entry in squad_entries:
            p: Player = entry.player
            t: Team = p.team
            squad_players.append(
                SquadPlayerResponse(
                    player_id=p.id,
                    fpl_id=p.fpl_id,
                    name=p.name,
                    first_name=p.first_name,
                    second_name=p.second_name,
                    team=t.short_name,
                    position=p.position,
                    price=p.price,
                    is_starting=entry.is_starting,
                    is_captain=entry.is_captain,
                    is_vice=entry.is_vice,
                )
            )

        return SquadResponse(
            user_id=user.id,
            fpl_entry_id=user.fpl_entry_id,
            gameweek=gameweek,
            squad=squad_players,
        )
