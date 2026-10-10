"""SQLAlchemy ORM models — the persistent game world.

Hierarchy: League -> Conference -> Division -> Team -> Player.
A Franchise is the user's career save: one controlled team inside a league.
"""

from datetime import UTC, datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def _now() -> datetime:
    return datetime.now(UTC)


class League(Base):
    __tablename__ = "leagues"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(80))
    abbreviation: Mapped[str] = mapped_column(String(8))
    salary_cap: Mapped[int] = mapped_column(Integer)  # whole dollars
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    conferences: Mapped[list["Conference"]] = relationship(
        back_populates="league", cascade="all, delete-orphan", order_by="Conference.id"
    )
    teams: Mapped[list["Team"]] = relationship(back_populates="league", order_by="Team.id")
    seasons: Mapped[list["Season"]] = relationship(
        back_populates="league", cascade="all, delete-orphan", order_by="Season.year"
    )


class Conference(Base):
    __tablename__ = "conferences"

    id: Mapped[int] = mapped_column(primary_key=True)
    league_id: Mapped[int] = mapped_column(ForeignKey("leagues.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(60))
    abbreviation: Mapped[str] = mapped_column(String(8))

    league: Mapped[League] = relationship(back_populates="conferences")
    divisions: Mapped[list["Division"]] = relationship(
        back_populates="conference", cascade="all, delete-orphan", order_by="Division.id"
    )


class Division(Base):
    __tablename__ = "divisions"

    id: Mapped[int] = mapped_column(primary_key=True)
    conference_id: Mapped[int] = mapped_column(ForeignKey("conferences.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(60))

    conference: Mapped[Conference] = relationship(back_populates="divisions")
    teams: Mapped[list["Team"]] = relationship(back_populates="division", order_by="Team.id")


class Team(Base):
    __tablename__ = "teams"
    __table_args__ = (UniqueConstraint("league_id", "abbreviation"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    league_id: Mapped[int] = mapped_column(ForeignKey("leagues.id", ondelete="CASCADE"))
    division_id: Mapped[int] = mapped_column(ForeignKey("divisions.id", ondelete="CASCADE"))
    city: Mapped[str] = mapped_column(String(60))
    nickname: Mapped[str] = mapped_column(String(60))
    abbreviation: Mapped[str] = mapped_column(String(4))
    primary_color: Mapped[str] = mapped_column(String(7))  # "#RRGGBB"
    secondary_color: Mapped[str] = mapped_column(String(7))
    stadium: Mapped[str] = mapped_column(String(80))

    league: Mapped[League] = relationship(back_populates="teams")
    division: Mapped[Division] = relationship(back_populates="teams")
    players: Mapped[list["Player"]] = relationship(back_populates="team")

    @property
    def full_name(self) -> str:
        return f"{self.city} {self.nickname}"


class Player(Base):
    __tablename__ = "players"
    __table_args__ = (
        CheckConstraint("overall BETWEEN 0 AND 99", name="ck_players_overall_range"),
        CheckConstraint("potential BETWEEN 0 AND 99", name="ck_players_potential_range"),
        CheckConstraint("jersey_number BETWEEN 0 AND 99", name="ck_players_jersey_range"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    league_id: Mapped[int] = mapped_column(ForeignKey("leagues.id", ondelete="CASCADE"))
    # NULL team = free agent.
    team_id: Mapped[int | None] = mapped_column(
        ForeignKey("teams.id", ondelete="SET NULL"), index=True
    )
    first_name: Mapped[str] = mapped_column(String(40))
    last_name: Mapped[str] = mapped_column(String(40))
    position: Mapped[str] = mapped_column(String(4), index=True)
    jersey_number: Mapped[int] = mapped_column(Integer)
    age: Mapped[int] = mapped_column(Integer)
    height_in: Mapped[int] = mapped_column(Integer)
    weight_lb: Mapped[int] = mapped_column(Integer)
    college: Mapped[str] = mapped_column(String(60))
    years_pro: Mapped[int] = mapped_column(Integer, default=0)
    overall: Mapped[int] = mapped_column(Integer, index=True)  # cached from ratings
    potential: Mapped[int] = mapped_column(Integer)
    development_trait: Mapped[str] = mapped_column(String(12), default="normal")
    injury_status: Mapped[str] = mapped_column(String(12), default="healthy")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    league: Mapped[League] = relationship()
    team: Mapped[Team | None] = relationship(back_populates="players")
    ratings: Mapped["PlayerRatings"] = relationship(
        back_populates="player", cascade="all, delete-orphan", uselist=False
    )
    contracts: Mapped[list["Contract"]] = relationship(
        back_populates="player", cascade="all, delete-orphan"
    )

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}"

    @property
    def active_contract(self) -> "Contract | None":
        return next((c for c in self.contracts if c.is_active), None)


class PlayerRatings(Base):
    """One row per player; column names match app.domain.ratings.ATTRIBUTES."""

    __tablename__ = "player_ratings"

    player_id: Mapped[int] = mapped_column(
        ForeignKey("players.id", ondelete="CASCADE"), primary_key=True
    )
    speed: Mapped[int] = mapped_column(Integer)
    acceleration: Mapped[int] = mapped_column(Integer)
    strength: Mapped[int] = mapped_column(Integer)
    agility: Mapped[int] = mapped_column(Integer)
    stamina: Mapped[int] = mapped_column(Integer)
    toughness: Mapped[int] = mapped_column(Integer)
    awareness: Mapped[int] = mapped_column(Integer)
    throw_power: Mapped[int] = mapped_column(Integer)
    throw_accuracy: Mapped[int] = mapped_column(Integer)
    carrying: Mapped[int] = mapped_column(Integer)
    ball_carrier_vision: Mapped[int] = mapped_column(Integer)
    elusiveness: Mapped[int] = mapped_column(Integer)
    catching: Mapped[int] = mapped_column(Integer)
    route_running: Mapped[int] = mapped_column(Integer)
    run_blocking: Mapped[int] = mapped_column(Integer)
    pass_blocking: Mapped[int] = mapped_column(Integer)
    tackling: Mapped[int] = mapped_column(Integer)
    pass_rush: Mapped[int] = mapped_column(Integer)
    block_shedding: Mapped[int] = mapped_column(Integer)
    man_coverage: Mapped[int] = mapped_column(Integer)
    zone_coverage: Mapped[int] = mapped_column(Integer)
    play_recognition: Mapped[int] = mapped_column(Integer)
    kick_power: Mapped[int] = mapped_column(Integer)
    kick_accuracy: Mapped[int] = mapped_column(Integer)

    player: Mapped[Player] = relationship(back_populates="ratings")

    def as_dict(self) -> dict[str, int]:
        from app.domain.ratings import ATTRIBUTES

        return {name: getattr(self, name) for name in ATTRIBUTES}


class DepthChartEntry(Base):
    """A user-customized depth chart slot: one row per (team, slot, depth).

    Only customized slots are stored; a slot with no rows is ordered by OVR.
    A player may be listed at slots other than their own position (cross-listing).
    """

    __tablename__ = "depth_chart_entries"
    __table_args__ = (
        UniqueConstraint("team_id", "slot", "depth", name="uq_depth_chart_team_slot_depth"),
        UniqueConstraint("team_id", "slot", "player_id", name="uq_depth_chart_team_slot_player"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id", ondelete="CASCADE"), index=True)
    slot: Mapped[str] = mapped_column(String(4))  # a Position value
    depth: Mapped[int] = mapped_column(Integer)  # 1 = first string
    player_id: Mapped[int] = mapped_column(ForeignKey("players.id", ondelete="CASCADE"))


class Contract(Base):
    __tablename__ = "contracts"

    id: Mapped[int] = mapped_column(primary_key=True)
    player_id: Mapped[int] = mapped_column(ForeignKey("players.id", ondelete="CASCADE"))
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id", ondelete="CASCADE"))
    start_year: Mapped[int] = mapped_column(Integer)
    years: Mapped[int] = mapped_column(Integer)
    salary: Mapped[int] = mapped_column(Integer)  # per season, whole dollars
    signing_bonus: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(default=True)

    player: Mapped[Player] = relationship(back_populates="contracts")

    @property
    def end_year(self) -> int:
        return self.start_year + self.years - 1


class Season(Base):
    __tablename__ = "seasons"
    __table_args__ = (UniqueConstraint("league_id", "year"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    league_id: Mapped[int] = mapped_column(ForeignKey("leagues.id", ondelete="CASCADE"))
    year: Mapped[int] = mapped_column(Integer)
    # preseason | regular_season | playoffs | offseason
    phase: Mapped[str] = mapped_column(String(20), default="preseason")
    current_week: Mapped[int] = mapped_column(Integer, default=1)

    league: Mapped[League] = relationship(back_populates="seasons")
    games: Mapped[list["Game"]] = relationship(
        back_populates="season", cascade="all, delete-orphan", order_by="Game.week"
    )


class Game(Base):
    __tablename__ = "games"

    id: Mapped[int] = mapped_column(primary_key=True)
    season_id: Mapped[int] = mapped_column(ForeignKey("seasons.id", ondelete="CASCADE"))
    week: Mapped[int] = mapped_column(Integer, index=True)
    home_team_id: Mapped[int] = mapped_column(ForeignKey("teams.id", ondelete="CASCADE"))
    away_team_id: Mapped[int] = mapped_column(ForeignKey("teams.id", ondelete="CASCADE"))
    home_score: Mapped[int | None] = mapped_column(Integer)
    away_score: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(12), default="scheduled")  # scheduled | final

    season: Mapped[Season] = relationship(back_populates="games")
    home_team: Mapped[Team] = relationship(foreign_keys=[home_team_id])
    away_team: Mapped[Team] = relationship(foreign_keys=[away_team_id])


class Franchise(Base):
    """The user's career save: which league and which team they control."""

    __tablename__ = "franchises"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(80))
    league_id: Mapped[int] = mapped_column(ForeignKey("leagues.id", ondelete="CASCADE"))
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id", ondelete="CASCADE"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    league: Mapped[League] = relationship()
    team: Mapped[Team] = relationship()
