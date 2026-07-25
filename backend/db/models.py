from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Base declarative class for all database models."""

    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    fpl_entry_id: Mapped[int | None] = mapped_column(
        unique=True, nullable=True, index=True
    )
    risk_profile: Mapped[str] = mapped_column(String(50), default="balanced")
    encrypted_session_token: Mapped[str | None] = mapped_column(
        String(255), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    # Relationships
    squads: Mapped[list["UserSquad"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    transfer_states: Mapped[list["UserTransferState"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class Team(Base):
    __tablename__ = "teams"

    id: Mapped[int] = mapped_column(primary_key=True)
    fpl_id: Mapped[int] = mapped_column(unique=True, index=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    short_name: Mapped[str] = mapped_column(String(10))

    # Relationships
    players: Mapped[list["Player"]] = relationship(back_populates="team")


class Player(Base):
    __tablename__ = "players"

    id: Mapped[int] = mapped_column(primary_key=True)
    fpl_id: Mapped[int] = mapped_column(unique=True, index=True)
    name: Mapped[str] = mapped_column(String(100))  # web name (commonly used name)
    first_name: Mapped[str] = mapped_column(String(100))
    second_name: Mapped[str] = mapped_column(String(100))
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"))
    position: Mapped[str] = mapped_column(
        String(10)
    )  # e.g., "GKP", "DEF", "MID", "FWD"
    price: Mapped[int] = mapped_column()  # in tenths of a million, e.g. 55 = £5.5m
    status: Mapped[str] = mapped_column(String(10))  # e.g., "a", "i", "d"
    chance_of_playing_next_round: Mapped[int | None] = mapped_column(nullable=True)
    chance_of_playing_this_round: Mapped[int | None] = mapped_column(nullable=True)
    news: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Relationships
    team: Mapped["Team"] = relationship(back_populates="players")
    gameweek_stats: Mapped[list["GameweekStat"]] = relationship(
        back_populates="player", cascade="all, delete-orphan"
    )
    squad_entries: Mapped[list["UserSquad"]] = relationship(
        back_populates="player", cascade="all, delete-orphan"
    )


class Fixture(Base):
    __tablename__ = "fixtures"

    id: Mapped[int] = mapped_column(primary_key=True)
    fpl_id: Mapped[int] = mapped_column(unique=True, index=True)
    gameweek: Mapped[int] = mapped_column(index=True)
    home_team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"))
    away_team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"))
    difficulty_home: Mapped[int] = mapped_column()
    difficulty_away: Mapped[int] = mapped_column()
    kickoff_time: Mapped[datetime] = mapped_column(DateTime)
    status: Mapped[str] = mapped_column(String(50))  # e.g., "upcoming", "finished"

    # Relationships
    home_team: Mapped["Team"] = relationship(foreign_keys=[home_team_id])
    away_team: Mapped["Team"] = relationship(foreign_keys=[away_team_id])


class GameweekStat(Base):
    __tablename__ = "gameweek_stats"

    id: Mapped[int] = mapped_column(primary_key=True)
    player_id: Mapped[int] = mapped_column(ForeignKey("players.id"))
    gameweek: Mapped[int] = mapped_column(index=True)
    minutes: Mapped[int] = mapped_column(default=0)
    goals: Mapped[int] = mapped_column(default=0)
    assists: Mapped[int] = mapped_column(default=0)
    xg: Mapped[float] = mapped_column(Float, default=0.0)
    xa: Mapped[float] = mapped_column(Float, default=0.0)
    bonus: Mapped[int] = mapped_column(default=0)
    total_points: Mapped[int] = mapped_column(default=0)

    # Relationships
    player: Mapped["Player"] = relationship(back_populates="gameweek_stats")

    __table_args__ = (
        UniqueConstraint("player_id", "gameweek", name="uq_player_gameweek"),
    )


class UserSquad(Base):
    __tablename__ = "user_squads"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    gameweek: Mapped[int] = mapped_column(index=True)
    player_id: Mapped[int] = mapped_column(ForeignKey("players.id"))
    is_starting: Mapped[bool] = mapped_column(Boolean, default=False)
    is_captain: Mapped[bool] = mapped_column(Boolean, default=False)
    is_vice: Mapped[bool] = mapped_column(Boolean, default=False)

    # Relationships
    user: Mapped["User"] = relationship(back_populates="squads")
    player: Mapped["Player"] = relationship(back_populates="squad_entries")

    __table_args__ = (
        UniqueConstraint(
            "user_id", "gameweek", "player_id", name="uq_user_gameweek_player"
        ),
    )


class UserTransferState(Base):
    __tablename__ = "user_transfer_state"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    gameweek: Mapped[int] = mapped_column(index=True)
    free_transfers_banked: Mapped[int] = mapped_column(default=1)
    bank_balance: Mapped[int] = mapped_column(default=0)  # in tenths of a million

    # Relationships
    user: Mapped["User"] = relationship(back_populates="transfer_states")

    __table_args__ = (
        UniqueConstraint("user_id", "gameweek", name="uq_user_gameweek_transfer"),
    )


# ==============================================================================
# TODOs for Future Sprints (Do not implement schemas yet)
# ==============================================================================
# TODO: xp_predictions (Sprint 2 — Point prediction models and predictions storage)
# TODO: recommendations (Sprint 2 — ILP optimizer recommendations)
# TODO: recommendation_explanations (Sprint 3 — Grounded explanations
#       for recommendations)
# TODO: news_items (Sprint 4 — News Scraping and recency/confidence scoring)
# TODO: backtest_runs (Sprint 2 — Backtesting framework runs and results)
# TODO: auto_submit_log (Sprint 5 — Auto-submit transaction logs)
