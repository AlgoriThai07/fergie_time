"""
Unit tests for the baseline xP model (backend/models/baseline_xp.py).

Hand-computed expected values are documented inline so the test doubles as
a spec for the formula.  No DB required for the pure-function tests;
integration-style tests that touch the DB are in tests/integration/.
"""
import pytest
from unittest.mock import MagicMock, patch

# ---------------------------------------------------------------------------
# Pure-function tests (no DB)
# ---------------------------------------------------------------------------

from models.baseline_xp import _fdr_multiplier, MAX_WINDOW


class TestFdrMultiplier:
    """FDR → multiplier lookup, including edge cases."""

    def test_fdr_1_is_easiest(self):
        assert _fdr_multiplier(1) == pytest.approx(1.30)

    def test_fdr_5_is_hardest(self):
        assert _fdr_multiplier(5) == pytest.approx(0.70)

    def test_fdr_3_is_neutral(self):
        assert _fdr_multiplier(3) == pytest.approx(1.00)

    def test_fdr_none_blank_gameweek(self):
        # Blank gameweek → expect 0 points.
        assert _fdr_multiplier(None) == pytest.approx(0.0)

    def test_fdr_float_rounds_to_nearest(self):
        # Python's built-in round() uses banker's rounding (round-half-to-even):
        #   round(2.5) → 2  → multiplier 1.15
        #   round(3.5) → 4  → multiplier 0.85
        # The test documents this behaviour explicitly so it's not surprising later.
        assert _fdr_multiplier(2.5) == pytest.approx(1.15)   # 2.5 → 2 → 1.15
        assert _fdr_multiplier(3.5) == pytest.approx(0.85)   # 3.5 → 4 → 0.85

    def test_fdr_out_of_range_falls_back_to_neutral(self):
        # FDR 6 or 0 are not in the lookup; should fall back to 1.0.
        assert _fdr_multiplier(6) == pytest.approx(1.00)
        assert _fdr_multiplier(0) == pytest.approx(1.00)


# ---------------------------------------------------------------------------
# predict() — mocked DB
#
# Hand-computed values for two synthetic players:
#
# Player A (full window, FDR 2):
#   rolling_avg_points = 6.0, games_in_window = 5, fdr = 2.0
#   point_estimate = 6.0 × 1.15 = 6.90
#   confidence     = 5 / 5     = 1.00
#
# Player B (partial window, FDR 4):
#   rolling_avg_points = 3.0, games_in_window = 2, fdr = 4.0
#   point_estimate = 3.0 × 0.85 = 2.55
#   confidence     = 2 / 5      = 0.40
#
# Player C (new signing, no history, FDR 3):
#   rolling_avg_points = 0.0, games_in_window = 0, fdr = 3.0
#   point_estimate = 0.0 × 1.00 = 0.00
#   confidence     = 0 / 5      = 0.00
#
# Player D (blank gameweek, full history):
#   rolling_avg_points = 5.0, games_in_window = 5, fdr = None
#   point_estimate = 5.0 × 0.00 = 0.00   (blank GW multiplier)
#   confidence     = 5 / 5      = 1.00
# ---------------------------------------------------------------------------

def _make_feature(rolling_avg_points, upcoming_fixture_difficulty):
    feat = MagicMock()
    feat.rolling_avg_points = rolling_avg_points
    feat.upcoming_fixture_difficulty = upcoming_fixture_difficulty
    return feat


def _mock_session(feature, history_count):
    """Return a mock context-manager session that yields consistent data."""
    session = MagicMock()
    # feature query
    session.query.return_value.filter_by.return_value.first.return_value = feature
    # history count query
    session.query.return_value.filter.return_value.count.return_value = history_count
    ctx = MagicMock()
    ctx.__enter__ = MagicMock(return_value=session)
    ctx.__exit__ = MagicMock(return_value=False)
    return ctx


@patch("models.baseline_xp.get_db_session")
class TestPredict:
    def test_player_a_full_window_easy_fixture(self, mock_get_session):
        """Player A: 5 games, rolling avg 6.0, FDR 2 → 6.90 pts, confidence 1.0."""
        mock_get_session.return_value = _mock_session(
            feature=_make_feature(rolling_avg_points=6.0, upcoming_fixture_difficulty=2.0),
            history_count=5,
        )
        from models.baseline_xp import predict
        pt_est, conf = predict(player_id=1, gameweek=10)
        # 6.0 × 1.15 = 6.90
        assert pt_est == pytest.approx(6.90)
        assert conf == pytest.approx(1.00)

    def test_player_b_partial_window_hard_fixture(self, mock_get_session):
        """Player B: 2 games, rolling avg 3.0, FDR 4 → 2.55 pts, confidence 0.4."""
        mock_get_session.return_value = _mock_session(
            feature=_make_feature(rolling_avg_points=3.0, upcoming_fixture_difficulty=4.0),
            history_count=2,
        )
        from models.baseline_xp import predict
        pt_est, conf = predict(player_id=2, gameweek=10)
        # 3.0 × 0.85 = 2.55
        assert pt_est == pytest.approx(2.55)
        assert conf == pytest.approx(0.40)

    def test_player_c_new_signing_no_history(self, mock_get_session):
        """Player C: 0 games, rolling avg 0.0, FDR 3 → 0.0 pts, confidence 0.0."""
        mock_get_session.return_value = _mock_session(
            feature=_make_feature(rolling_avg_points=0.0, upcoming_fixture_difficulty=3.0),
            history_count=0,
        )
        from models.baseline_xp import predict
        pt_est, conf = predict(player_id=3, gameweek=10)
        assert pt_est == pytest.approx(0.00)
        assert conf == pytest.approx(0.00)

    def test_player_d_blank_gameweek(self, mock_get_session):
        """Player D: blank GW (fdr=None) → 0 pts even with full history; confidence 1.0."""
        mock_get_session.return_value = _mock_session(
            feature=_make_feature(rolling_avg_points=5.0, upcoming_fixture_difficulty=None),
            history_count=5,
        )
        from models.baseline_xp import predict
        pt_est, conf = predict(player_id=4, gameweek=10)
        assert pt_est == pytest.approx(0.00)
        assert conf == pytest.approx(1.00)

    def test_missing_feature_row_returns_zero(self, mock_get_session):
        """No player_features row → (0.0, 0.0) with a warning, no exception."""
        mock_get_session.return_value = _mock_session(
            feature=None,   # simulates missing row
            history_count=0,
        )
        from models.baseline_xp import predict
        pt_est, conf = predict(player_id=99, gameweek=10)
        assert pt_est == pytest.approx(0.00)
        assert conf == pytest.approx(0.00)

    def test_history_count_capped_at_max_window(self, mock_get_session):
        """If a player has 10 historical games, confidence is still capped at 1.0."""
        mock_get_session.return_value = _mock_session(
            feature=_make_feature(rolling_avg_points=4.0, upcoming_fixture_difficulty=3.0),
            history_count=10,  # more than MAX_WINDOW=5
        )
        from models.baseline_xp import predict
        pt_est, conf = predict(player_id=5, gameweek=10)
        # 4.0 × 1.00 = 4.00
        assert pt_est == pytest.approx(4.00)
        assert conf == pytest.approx(1.00)  # capped at MAX_WINDOW/MAX_WINDOW = 1.0
