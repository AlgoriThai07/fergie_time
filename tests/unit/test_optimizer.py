"""
Unit tests for backend/optimization/optimizer.py.

All tests use purely synthetic data — no database, no network.
CBC solver must be installed (pulp[cbc]) for these tests to pass.
"""
import time

import pytest

from optimization.optimizer import PlayerData, optimize_lineup, optimize_transfers

# ---------------------------------------------------------------------------
# Helpers: build synthetic squads
# ---------------------------------------------------------------------------

_GID = 0  # global auto-increment for unique player_ids


def _pid():
    global _GID
    _GID += 1
    return _GID


def _p(pos: str, team_id: int = 1, price: int = 60, xp: float = 5.0, name: str | None = None) -> PlayerData:
    pid = _pid()
    return PlayerData(
        player_id=pid,
        name=name or f"{pos}_{pid}",
        position=pos,
        team_id=team_id,
        price=price,
    ), pid, xp


def _build_squad_15(
    gkp_count=2, def_count=5, mid_count=5, fwd_count=3,
    price=60, xp=5.0
):
    """Return (players, xp_map) for a valid 15-player squad.

    Players are spread across teams 1..5 (3 per team) so the club-cap
    constraint is never violated by the squad itself.
    """
    players, xp_map = [], {}
    team_cycle = [1, 2, 3, 4, 5]  # 3 players each → exactly legal
    spec = (
        [("GKP", gkp_count), ("DEF", def_count), ("MID", mid_count), ("FWD", fwd_count)]
    )
    idx = 0
    for pos, count in spec:
        for _ in range(count):
            tid = team_cycle[idx % len(team_cycle)]
            idx += 1
            p, pid, x = _p(pos, team_id=tid, price=price, xp=xp)
            players.append(p)
            xp_map[pid] = x
    return players, xp_map


# ---------------------------------------------------------------------------
# optimize_lineup — correctness
# ---------------------------------------------------------------------------

class TestOptimizeLineup:

    def _result_ok(self, result, squad):
        xi = result["starting_xi"]
        bench = result["bench"]
        assert len(xi) == 11
        assert len(bench) == 4
        # No overlap between starting XI and bench
        xi_ids = {p.player_id for p in xi}
        bench_ids = {p.player_id for p in bench}
        assert xi_ids.isdisjoint(bench_ids)
        # Together they cover the full squad
        squad_ids = {p.player_id for p in squad}
        assert xi_ids | bench_ids == squad_ids

    def test_basic_valid_lineup(self):
        squad, xp_map = _build_squad_15()
        result = optimize_lineup(squad, xp_map)
        self._result_ok(result, squad)

    def test_exactly_one_gk_starts(self):
        squad, xp_map = _build_squad_15()
        result = optimize_lineup(squad, xp_map)
        gk_in_xi = [p for p in result["starting_xi"] if p.position == "GKP"]
        assert len(gk_in_xi) == 1

    def test_formation_within_valid_ranges(self):
        squad, xp_map = _build_squad_15()
        result = optimize_lineup(squad, xp_map)
        xi = result["starting_xi"]
        counts = {pos: sum(1 for p in xi if p.position == pos)
                  for pos in ("GKP", "DEF", "MID", "FWD")}
        assert counts["GKP"] == 1
        assert 3 <= counts["DEF"] <= 5
        assert 2 <= counts["MID"] <= 5
        assert 1 <= counts["FWD"] <= 3
        assert sum(counts.values()) == 11

    def test_maximises_xp_high_xp_players_start(self):
        """Players with high xP should be picked into the XI."""
        squad, xp_map = _build_squad_15()

        # Give two DEFs very high xP — they must start
        high_xp_players = [p for p in squad if p.position == "DEF"][:2]
        for p in high_xp_players:
            xp_map[p.player_id] = 50.0   # much higher than default 5.0

        result = optimize_lineup(squad, xp_map)
        xi_ids = {p.player_id for p in result["starting_xi"]}
        for p in high_xp_players:
            assert p.player_id in xi_ids, f"{p.name} should start due to high xP"

    def test_bench_gk_is_first(self):
        """Bench ordering should have the GK first."""
        squad, xp_map = _build_squad_15()
        result = optimize_lineup(squad, xp_map)
        assert result["bench"][0].position == "GKP"

    def test_wrong_squad_size_raises(self):
        squad, xp_map = _build_squad_15()
        with pytest.raises(ValueError, match="15"):
            optimize_lineup(squad[:14], xp_map)

    def test_formation_string_format(self):
        squad, xp_map = _build_squad_15()
        result = optimize_lineup(squad, xp_map)
        # e.g. "1-4-4-2" or "1-3-5-2"
        parts = result["formation"].split("-")
        assert len(parts) == 4
        assert parts[0] == "1"  # always 1 GK

    def test_solve_time_under_one_second(self):
        squad, xp_map = _build_squad_15()
        t0 = time.monotonic()
        optimize_lineup(squad, xp_map)
        assert time.monotonic() - t0 < 1.0, "optimize_lineup took more than 1 second"


# ---------------------------------------------------------------------------
# optimize_transfers — correctness
# ---------------------------------------------------------------------------

class TestOptimizeTransfers:

    def _assert_valid_squad(self, new_squad):
        assert len(new_squad) == 15
        counts = {pos: sum(1 for p in new_squad if p.position == pos)
                  for pos in ("GKP", "DEF", "MID", "FWD")}
        assert counts["GKP"] == 2
        assert counts["DEF"] == 5
        assert counts["MID"] == 5
        assert counts["FWD"] == 3

    def _assert_club_limit(self, new_squad):
        from collections import Counter
        team_counts = Counter(p.team_id for p in new_squad)
        for tid, count in team_counts.items():
            assert count <= 3, f"Club {tid} has {count} players (limit 3)"

    def test_basic_no_transfers_needed(self):
        """If current squad is already optimal, no transfers should happen."""
        squad, xp_map = _build_squad_15()
        # all_players is exactly the current squad → no better swap exists
        result = optimize_transfers(
            current_squad=squad,
            all_players=squad,
            xp_map=xp_map,
            budget=0,
            max_transfers=1,
        )
        self._assert_valid_squad(result["new_squad"])
        assert len(result["transfers_in"]) == 0
        assert len(result["transfers_out"]) == 0

    def test_transfer_improves_squad_xp(self):
        """
        A clearly better player available: optimizer should swap them in.
        """
        squad, xp_map = _build_squad_15(price=60, xp=5.0)

        # One expensive FWD with low xP in the current squad
        weak_fwd = next(p for p in squad if p.position == "FWD")
        xp_map[weak_fwd.player_id] = 1.0

        # Create a much better, affordable replacement FWD
        better_fwd, bfwd_id, _ = _p("FWD", team_id=99, price=55, xp=12.0)
        xp_map[bfwd_id] = 12.0

        all_players = squad + [better_fwd]
        result = optimize_transfers(
            current_squad=squad,
            all_players=all_players,
            xp_map=xp_map,
            budget=50,        # plenty of room
            max_transfers=1,
        )
        self._assert_valid_squad(result["new_squad"])
        self._assert_club_limit(result["new_squad"])
        assert better_fwd in result["new_squad"], "Better FWD should be brought in"
        assert weak_fwd not in result["new_squad"], "Weak FWD should be transferred out"

    def test_budget_constraint_respected(self):
        """
        No transfers should happen when the budget is zero and the only
        available swap is more expensive than the current player.
        """
        squad, xp_map = _build_squad_15(price=60, xp=5.0)

        expensive_fwd, efid, _ = _p("FWD", team_id=99, price=150, xp=20.0)
        xp_map[efid] = 20.0

        all_players = squad + [expensive_fwd]
        result = optimize_transfers(
            current_squad=squad,
            all_players=all_players,
            xp_map=xp_map,
            budget=0,
            max_transfers=1,
        )
        self._assert_valid_squad(result["new_squad"])
        squad_ids = {p.player_id for p in result["new_squad"]}
        assert efid not in squad_ids, "Expensive player shouldn't be bought with zero budget"

    def test_club_cap_enforced(self):
        """
        When a club already has 3 players in the current squad, a fourth from
        that club must not be selected even if their xP is very high.

        Scenario:
          - Club 999 already has GKP + DEF + FWD in the squad (3 = cap).
          - We offer a very high-xP MID from club 999 as a transfer-in,
            targeting one of the non-club-999 MID slots.
          - Post-transfer the squad would contain 4 club-999 players → must be blocked.
        """
        players = []
        xp_map = {}

        def add(pos, team_id, price=60, xp=5.0):
            p, pid, _ = _p(pos, team_id=team_id, price=price, xp=xp)
            xp_map[pid] = xp
            players.append(p)

        # Club 999 holds exactly 3 spots (GKP, DEF, FWD)
        add("GKP", 999)
        add("DEF", 999)
        add("FWD", 999)

        # Remaining 12 slots on distinct clubs
        add("GKP", 10)
        add("DEF", 11); add("DEF", 12); add("DEF", 13); add("DEF", 14)
        add("MID", 15); add("MID", 16); add("MID", 17); add("MID", 18); add("MID", 19)
        add("FWD", 20); add("FWD", 21)

        squad = players
        assert len(squad) == 15

        # A MID from club 999 with enormous xP — bringing them in (to replace any
        # non-999 MID) would create 4 players from club 999 → must be blocked.
        tempting, tid, _ = _p("MID", team_id=999, price=50, xp=100.0)
        xp_map[tid] = 100.0

        all_players = squad + [tempting]
        result = optimize_transfers(
            current_squad=squad,
            all_players=all_players,
            xp_map=xp_map,
            budget=200,
            max_transfers=1,
        )
        self._assert_valid_squad(result["new_squad"])
        self._assert_club_limit(result["new_squad"])
        squad_ids = {p.player_id for p in result["new_squad"]}
        assert tid not in squad_ids, "4th player from same club must not be selected"

    def test_max_transfers_respected(self):
        """No more than max_transfers players should be exchanged."""
        squad, xp_map = _build_squad_15(price=50, xp=2.0)

        # Create 5 much better alternatives across different clubs
        alternates = []
        for i, pos in enumerate(["GKP", "DEF", "MID", "FWD", "FWD"]):
            p, pid, _ = _p(pos, team_id=50 + i, price=45, xp=30.0)
            xp_map[pid] = 30.0
            alternates.append(p)

        all_players = squad + alternates
        for n in (1, 2):
            result = optimize_transfers(
                current_squad=squad,
                all_players=all_players,
                xp_map=xp_map,
                budget=500,
                max_transfers=n,
            )
            self._assert_valid_squad(result["new_squad"])
            assert len(result["transfers_out"]) <= n, (
                f"Expected at most {n} transfers out, got {len(result['transfers_out'])}"
            )

    def test_wrong_squad_size_raises(self):
        squad, xp_map = _build_squad_15()
        with pytest.raises(ValueError, match="15"):
            optimize_transfers(squad[:14], squad, xp_map, budget=100, max_transfers=1)

    def test_solve_time_under_one_second_20_candidate_pool(self):
        """Transfer optimisation on a ~20-player pool should be well under 1 second."""
        squad, xp_map = _build_squad_15(price=60, xp=5.0)
        extras = []
        for i in range(5):
            pos = ["GKP", "DEF", "MID", "FWD", "MID"][i]
            p, pid, _ = _p(pos, team_id=20 + i, price=55, xp=7.0)
            xp_map[pid] = 7.0
            extras.append(p)

        all_players = squad + extras
        t0 = time.monotonic()
        optimize_transfers(
            current_squad=squad,
            all_players=all_players,
            xp_map=xp_map,
            budget=100,
            max_transfers=2,
        )
        elapsed = time.monotonic() - t0
        assert elapsed < 1.0, f"optimize_transfers took {elapsed:.2f}s (limit 1s)"
