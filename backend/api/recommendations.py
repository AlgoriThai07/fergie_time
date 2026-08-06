import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from api.squad import _fetch_and_persist_squad
from db.models import Player, User, UserSquad, UserTransferState, XpPrediction
from db.session import get_db_session
from optimization.optimizer import PlayerData, optimize_lineup, optimize_transfers

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/recommendations", tags=["recommendations"])


# ---------------------------------------------------------------------------
# Response Schemas
# ---------------------------------------------------------------------------


class PlayerRecommendationResponse(BaseModel):
    """Pydantic model representing a player in recommendation results."""

    player_id: int
    fpl_id: int
    name: str
    team: str
    position: str
    price: int
    xp: float


class RecommendedLineup(BaseModel):
    """Lineup recommendations including starting XI, bench, and formation."""

    starting_xi: list[PlayerRecommendationResponse]
    bench: list[PlayerRecommendationResponse]
    formation: str


class RecommendedTransfer(BaseModel):
    """Recommended transfer swap and projected xP gain."""

    transfer_in: PlayerRecommendationResponse
    transfer_out: PlayerRecommendationResponse
    xp_gain: float


class RecommendationsResponse(BaseModel):
    """Top-level recommendations response."""

    user_id: int
    gameweek: int
    bank_balance: int
    lineup: RecommendedLineup
    transfer: RecommendedTransfer | None
    xp_map: dict[int, float]


# ---------------------------------------------------------------------------
# Route
# ---------------------------------------------------------------------------


@router.get("/{user_id}/{gameweek}", response_model=RecommendationsResponse)
def get_recommendations(user_id: int, gameweek: int, max_transfers: int = 1):
    """
    Get squad recommendations (starting XI, bench order, suggested transfer)
    for a given FPL entry ID and target gameweek.
    """
    with get_db_session() as session:
        # Determine the squad gameweek (the one before target gameweek)
        squad_gw = gameweek - 1 if gameweek > 1 else 1

        # Load the user by FPL entry ID
        user = session.query(User).filter_by(fpl_entry_id=user_id).first()

        # Load squad from database
        if user:
            squad_entries = (
                session.query(UserSquad)
                .filter_by(user_id=user.id, gameweek=squad_gw)
                .all()
            )
        else:
            squad_entries = []

        # Fallback: live fetch and persist squad if not found in database
        if not squad_entries:
            try:
                user = _fetch_and_persist_squad(user_id, squad_gw, session)
                squad_entries = (
                    session.query(UserSquad)
                    .filter_by(user_id=user.id, gameweek=squad_gw)
                    .all()
                )
            except Exception as exc:
                logger.error(
                    "Live squad fetch failed for fpl_entry_id=%d in gameweek %d: %s",
                    user_id,
                    squad_gw,
                    exc,
                )
                raise HTTPException(
                    status_code=503,
                    detail=(
                        f"User squad not found for gameweek {squad_gw} "
                        "and live FPL fetch failed."
                    ),
                ) from exc

        if not squad_entries:
            raise HTTPException(
                status_code=404,
                detail=(
                    f"No squad found for FPL entry id {user_id} in gameweek {squad_gw}."
                ),
            )

        # Query xP predictions for target gameweek (baseline model)
        predictions = (
            session.query(XpPrediction)
            .filter_by(gameweek=gameweek, model_version="baseline_v1")
            .all()
        )

        if not predictions:
            raise HTTPException(
                status_code=409,
                detail=(
                    f"xP predictions are missing for gameweek {gameweek}. "
                    "Please run the prediction tasks first."
                ),
            )

        # Create map of player_id -> predicted_points
        xp_map = {pred.player_id: pred.predicted_points for pred in predictions}

        # Query budget (bank balance) from previous gameweek
        transfer_state = (
            session.query(UserTransferState)
            .filter_by(user_id=user.id, gameweek=squad_gw)
            .first()
        )
        budget = 0
        if transfer_state:
            budget = transfer_state.bank_balance
        else:
            # Fallback to the latest available transfer state bank balance
            latest_state = (
                session.query(UserTransferState)
                .filter_by(user_id=user.id)
                .order_by(UserTransferState.gameweek.desc())
                .first()
            )
            if latest_state:
                budget = latest_state.bank_balance

        # Map DB players to PlayerData instances for optimizers
        squad_players_data = []
        for entry in squad_entries:
            p = entry.player
            squad_players_data.append(
                PlayerData(
                    player_id=p.id,
                    name=p.name,
                    position=p.position,
                    team_id=p.team_id,
                    price=p.price,
                )
            )

        db_players = session.query(Player).all()
        all_players_data = [
            PlayerData(
                player_id=p.id,
                name=p.name,
                position=p.position,
                team_id=p.team_id,
                price=p.price,
            )
            for p in db_players
        ]

        # Run lineup optimizer
        try:
            lineup_result = optimize_lineup(squad_players_data, xp_map)
        except Exception as exc:
            logger.error("Lineup optimization failed: %s", exc)
            raise HTTPException(
                status_code=500,
                detail=f"Failed to optimize lineup: {exc}",
            ) from exc

        # Format player objects for Pydantic response
        player_dict = {p.id: p for p in db_players}

        def make_rec_player(pd: PlayerData) -> PlayerRecommendationResponse:
            p = player_dict[pd.player_id]
            t = p.team
            return PlayerRecommendationResponse(
                player_id=pd.player_id,
                fpl_id=p.fpl_id,
                name=pd.name,
                team=t.short_name,
                position=pd.position,
                price=pd.price,
                xp=xp_map.get(pd.player_id, 0.0),
            )

        rec_starting_xi = [make_rec_player(pd) for pd in lineup_result["starting_xi"]]
        rec_bench = [make_rec_player(pd) for pd in lineup_result["bench"]]
        recommended_lineup = RecommendedLineup(
            starting_xi=rec_starting_xi,
            bench=rec_bench,
            formation=lineup_result["formation"],
        )

        # Run transfer optimizer
        try:
            transfer_result = optimize_transfers(
                squad_players_data,
                all_players_data,
                xp_map,
                budget,
                max_transfers=max_transfers,
            )
        except Exception as exc:
            logger.error("Transfer optimization failed: %s", exc)
            raise HTTPException(
                status_code=500,
                detail=f"Failed to optimize transfers: {exc}",
            ) from exc

        recommended_transfer = None
        if transfer_result["transfers_in"] and transfer_result["transfers_out"]:
            tin_pd = transfer_result["transfers_in"][0]
            tout_pd = transfer_result["transfers_out"][0]

            # Compute xP gain
            current_squad_xp = sum(
                xp_map.get(p.player_id, 0.0) for p in squad_players_data
            )
            new_squad_xp = sum(
                xp_map.get(p.player_id, 0.0) for p in transfer_result["new_squad"]
            )
            xp_gain = new_squad_xp - current_squad_xp

            recommended_transfer = RecommendedTransfer(
                transfer_in=make_rec_player(tin_pd),
                transfer_out=make_rec_player(tout_pd),
                xp_gain=round(xp_gain, 2),
            )

        # Filter the underlying xp_map to only include squad players
        # to keep response size concise
        squad_player_ids = {pd.player_id for pd in squad_players_data}
        if recommended_transfer:
            squad_player_ids.add(recommended_transfer.transfer_in.player_id)
            squad_player_ids.add(recommended_transfer.transfer_out.player_id)

        filtered_xp_map = {pid: xp_map.get(pid, 0.0) for pid in squad_player_ids}

        return RecommendationsResponse(
            user_id=user.id,
            gameweek=gameweek,
            bank_balance=budget,
            lineup=recommended_lineup,
            transfer=recommended_transfer,
            xp_map=filtered_xp_map,
        )
