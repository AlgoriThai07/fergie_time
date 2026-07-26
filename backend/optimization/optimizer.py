"""
ILP optimizer for FPL lineup selection and transfer recommendations.

Uses PuLP with the CBC solver (installed via pulp[cbc]).

Two public functions:
    optimize_lineup(squad_15_players, xp_map)
        -> {"starting_xi": [...], "bench": [...], "formation": str}

    optimize_transfers(current_squad, all_players, xp_map, budget, max_transfers)
        -> {"transfers_in": [...], "transfers_out": [...], "new_squad": [...]}

Both functions raise RuntimeError if CBC is not available, rather than letting
PuLP surface a cryptic internal error.  See _get_solver().
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any

import pulp

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------


@dataclass
class PlayerData:
    """Lightweight struct passed into the optimizer — no SQLAlchemy required."""

    player_id: int
    name: str
    position: str  # "GKP", "DEF", "MID", "FWD"
    team_id: int
    price: int  # tenths of £1m, e.g. 85 = £8.5m


# FPL squad composition requirements
_SQUAD_POS = {"GKP": 2, "DEF": 5, "MID": 5, "FWD": 3}  # 15 total
_LINEUP_POS_MIN = {"GKP": 1, "DEF": 3, "MID": 2, "FWD": 1}  # per-position minimums
_LINEUP_POS_MAX = {"GKP": 1, "DEF": 5, "MID": 5, "FWD": 3}  # per-position maximums
_LINEUP_SIZE = 11
_MAX_PER_CLUB = 3


# ---------------------------------------------------------------------------
# Solver bootstrap
# ---------------------------------------------------------------------------


def _get_solver() -> pulp.LpSolver:
    """Return a CBC solver instance, or raise a clear RuntimeError if not found.

    cbcbox (installed by pulp[cbc]) delivers the solver as the legacy
    PULP_CBC_CMD bundled binary.  COIN_CMD needs cbc.exe on the system PATH
    and is only tried as a fallback.
    msg=False suppresses solver stdout so logs stay clean.
    """
    for solver_name in ("PULP_CBC_CMD", "COIN_CMD"):
        try:
            solver = pulp.getSolver(solver_name, msg=False)
            if solver is not None and solver.available():
                return solver
        except Exception:
            continue
    raise RuntimeError(
        "CBC solver not available.  Install it with: pip install 'pulp[cbc]'."
    )


# ---------------------------------------------------------------------------
# optimize_lineup
# ---------------------------------------------------------------------------


def optimize_lineup(
    squad_15_players: list[PlayerData],
    xp_map: dict[int, float],
) -> dict[str, Any]:
    """
    Given a fixed 15-player squad and their expected-points values, choose the
    best valid starting XI and bench order.

    Valid FPL formations: exactly 1 GK, 3-5 DEF, 2-5 MID, 1-3 FWD, 11 total.

    Returns a dict with keys:
        "starting_xi"  : list[PlayerData] (11 players)
        "bench"        : list[PlayerData] (4 players, ordered worst→best bench)
        "formation"    : str, e.g. "1-4-4-2"

    Raises ValueError if squad_15_players doesn't contain exactly 15 players.
    Raises RuntimeError if CBC solver is not installed.
    """
    if len(squad_15_players) != 15:
        raise ValueError(
            f"optimize_lineup requires exactly 15 players, got {len(squad_15_players)}"
        )

    solver = _get_solver()
    t0 = time.monotonic()

    prob = pulp.LpProblem("optimize_lineup", pulp.LpMaximize)

    # Binary variable: 1 = player is in starting XI
    start = {
        p.player_id: pulp.LpVariable(f"start_{p.player_id}", cat="Binary")
        for p in squad_15_players
    }

    # Objective: maximise total xP of starting XI
    prob += pulp.lpSum(
        start[p.player_id] * xp_map.get(p.player_id, 0.0) for p in squad_15_players
    )

    # Exactly 11 starters
    prob += pulp.lpSum(start[p.player_id] for p in squad_15_players) == _LINEUP_SIZE

    # Per-position constraints
    for pos in ("GKP", "DEF", "MID", "FWD"):
        pos_players = [p for p in squad_15_players if p.position == pos]
        prob += (
            pulp.lpSum(start[p.player_id] for p in pos_players) >= _LINEUP_POS_MIN[pos]
        )
        prob += (
            pulp.lpSum(start[p.player_id] for p in pos_players) <= _LINEUP_POS_MAX[pos]
        )

    status = prob.solve(solver)

    elapsed = time.monotonic() - t0
    logger.info(
        "optimize_lineup: solver status=%s, time=%.3fs", pulp.LpStatus[status], elapsed
    )

    if status != pulp.LpStatusOptimal:
        raise RuntimeError(
            f"ILP infeasible or solver error: status={pulp.LpStatus[status]}"
        )

    starting_xi = [p for p in squad_15_players if pulp.value(start[p.player_id]) > 0.5]
    bench = [p for p in squad_15_players if pulp.value(start[p.player_id]) <= 0.5]
    # Bench is ordered: GK first (guaranteed), then outfield worst→best xP
    gk_bench = [p for p in bench if p.position == "GKP"]
    outfield_bench = sorted(
        [p for p in bench if p.position != "GKP"],
        key=lambda p: xp_map.get(p.player_id, 0.0),
    )
    bench_ordered = gk_bench + outfield_bench

    counts = {
        pos: sum(1 for p in starting_xi if p.position == pos)
        for pos in ("GKP", "DEF", "MID", "FWD")
    }
    formation = f"1-{counts['DEF']}-{counts['MID']}-{counts['FWD']}"

    return {
        "starting_xi": starting_xi,
        "bench": bench_ordered,
        "formation": formation,
    }


# ---------------------------------------------------------------------------
# optimize_transfers
# ---------------------------------------------------------------------------


def optimize_transfers(
    current_squad: list[PlayerData],
    all_players: list[PlayerData],
    xp_map: dict[int, float],
    budget: int,
    max_transfers: int,
) -> dict[str, Any]:
    """
    Find the best N-player swap (N ≤ max_transfers) that improves total squad xP.

    Constraints enforced on the *new* squad:
      - Valid position counts: 2 GKP, 5 DEF, 5 MID, 3 FWD
      - Max 3 players per club
      - Total cost ≤ current squad cost + budget (money in bank)

    Returns a dict with keys:
        "transfers_in"  : list[PlayerData] (players bought)
        "transfers_out" : list[PlayerData] (players sold)
        "new_squad"     : list[PlayerData] (full 15-player new squad)

    Returns empty lists for transfers_in/out if no beneficial swap is found.

    Raises RuntimeError if CBC solver is not installed or the problem is infeasible.
    """
    if len(current_squad) != 15:
        raise ValueError(
            "optimize_transfers requires exactly 15 current players, "
            f"got {len(current_squad)}"
        )

    solver = _get_solver()
    t0 = time.monotonic()

    current_ids = {p.player_id for p in current_squad}
    current_cost = sum(p.price for p in current_squad)
    spending_limit = current_cost + budget  # total squad value ceiling

    # Deduplicate all_players; current squad players are always candidates
    player_pool = {p.player_id: p for p in all_players}
    for p in current_squad:
        player_pool[p.player_id] = p
    players = list(player_pool.values())

    prob = pulp.LpProblem("optimize_transfers", pulp.LpMaximize)

    # Binary variable: 1 = player is in the new squad
    squad = {
        p.player_id: pulp.LpVariable(f"squad_{p.player_id}", cat="Binary")
        for p in players
    }

    # Objective: maximise total squad xP
    prob += pulp.lpSum(
        squad[p.player_id] * xp_map.get(p.player_id, 0.0) for p in players
    )

    # Exactly 15 players total
    prob += pulp.lpSum(squad[p.player_id] for p in players) == 15

    # Position quotas
    for pos, count in _SQUAD_POS.items():
        pos_players = [p for p in players if p.position == pos]
        prob += pulp.lpSum(squad[p.player_id] for p in pos_players) == count

    # Club limit: max 3 per real club
    team_ids = {p.team_id for p in players}
    for tid in team_ids:
        team_players = [p for p in players if p.team_id == tid]
        prob += pulp.lpSum(squad[p.player_id] for p in team_players) <= _MAX_PER_CLUB

    # Budget: total squad cost ≤ spending_limit
    prob += pulp.lpSum(p.price * squad[p.player_id] for p in players) <= spending_limit

    # Transfer count: total changes ≤ max_transfers
    # A player "transferred out" is one in current_squad but not in new squad.
    transfers_out_vars = [
        1 - squad[p.player_id] for p in players if p.player_id in current_ids
    ]
    prob += pulp.lpSum(transfers_out_vars) <= max_transfers

    status = prob.solve(solver)

    elapsed = time.monotonic() - t0
    logger.info(
        "optimize_transfers: solver status=%s, time=%.3fs",
        pulp.LpStatus[status],
        elapsed,
    )

    if status != pulp.LpStatusOptimal:
        raise RuntimeError(
            f"ILP infeasible or solver error: status={pulp.LpStatus[status]}"
        )

    new_squad = [p for p in players if pulp.value(squad[p.player_id]) > 0.5]
    new_ids = {p.player_id for p in new_squad}

    transfers_out = [p for p in current_squad if p.player_id not in new_ids]
    transfers_in = [p for p in new_squad if p.player_id not in current_ids]

    return {
        "transfers_in": transfers_in,
        "transfers_out": transfers_out,
        "new_squad": new_squad,
    }
