"""SQLAlchemy ORM models — the persistent game world.

Hierarchy: League -> Conference -> Division -> Team -> Player.
A Franchise is the user's career save: one controlled team inside a league.
"""

from datetime import UTC, datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    false,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.domain.contracts import signing_bonus


def _now() -> datetime:
    return datetime.now(UTC)


class User(Base):
    """An account: signs in with an email and a password, and owns leagues."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(254), unique=True)  # stored lower-case
    password_hash: Mapped[str] = mapped_column(String(200))  # Argon2
    # What other members of a shared league see (never the email). None: not set yet.
    display_name: Mapped[str | None] = mapped_column(String(40))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class UserSession(Base):
    """A signed-in browser. The cookie holds a random token; only its SHA-256 is stored, so
    a leaked table can't be used to sign in."""

    __tablename__ = "sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    user: Mapped[User] = relationship()


class PasswordReset(Base):
    """A password reset link sent by email: good once, for an hour. Only the SHA-256 of
    its token is stored."""

    __tablename__ = "password_resets"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class League(Base):
    __tablename__ = "leagues"

    id: Mapped[int] = mapped_column(primary_key=True)
    # Who created the league (its first commissioner). Who may see and change it is its
    # members (LeagueMember). Leagues from before accounts have none until the first
    # account created claims them.
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(80))
    abbreviation: Mapped[str] = mapped_column(String(8))
    salary_cap: Mapped[int] = mapped_column(Integer)  # whole dollars
    # Who plays: "men" or "women" (names and builds of generated players).
    players: Mapped[str] = mapped_column(String(8), default="men", server_default="men")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    # Leagues with friends (services/turns.py): how long a manager has to make a draft
    # pick, and the time of day (minutes after midnight UTC) the league advances itself,
    # if it does, with the last time it did.
    draft_clock_minutes: Mapped[int] = mapped_column(Integer, default=1440,
                                                     server_default="1440")
    advance_minute_utc: Mapped[int | None] = mapped_column(Integer)
    # Trades between managers wait this long for the commissioner's veto (0: they don't).
    trade_review_hours: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    auto_advanced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

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
    injury_status: Mapped[str] = mapped_column(String(20), default="healthy")
    # Set by simulated games: what it is and how many more games the player misses.
    injury: Mapped[str | None] = mapped_column(String(40))
    injury_weeks: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    # Career injuries from games (proneness: each one raises the odds of the next a little).
    injury_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    retired_year: Mapped[int | None] = mapped_column(Integer)  # last season played
    # Draft: prospects are in a class (draft_year) until drafted or let go after the draft.
    is_prospect: Mapped[bool] = mapped_column(default=False, server_default=false())
    scouted: Mapped[bool] = mapped_column(default=False, server_default=false())  # by the franchise
    draft_year: Mapped[int | None] = mapped_column(Integer)
    draft_round: Mapped[int | None] = mapped_column(Integer)
    draft_pick: Mapped[int | None] = mapped_column(Integer)  # overall pick number
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

    @classmethod
    def signed(cls, team_id: int, start_year: int, years: int, salary: int) -> "Contract":
        """A new deal: `salary` is its yearly cap hit; part of the money is a signing bonus
        (domain/contracts.signing_bonus) that becomes dead money if he's let go early."""
        return cls(team_id=team_id, start_year=start_year, years=years, salary=salary,
                   signing_bonus=signing_bonus(salary, years))

    @property
    def end_year(self) -> int:
        return self.start_year + self.years - 1


class Award(Base):
    """A season award (MVP, player and rookie of the year), decided when the season's
    champion is crowned (services/history.py)."""

    __tablename__ = "awards"
    __table_args__ = (UniqueConstraint("season_id", "award"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    season_id: Mapped[int] = mapped_column(ForeignKey("seasons.id", ondelete="CASCADE"),
                                           index=True)
    award: Mapped[str] = mapped_column(String(8))  # mvp | opoy | dpoy | oroy | droy
    player_id: Mapped[int] = mapped_column(ForeignKey("players.id", ondelete="CASCADE"))
    team_id: Mapped[int | None] = mapped_column(ForeignKey("teams.id", ondelete="SET NULL"))
    summary: Mapped[str] = mapped_column(String(120))  # "4,512 pass yds · 33 TD"

    player: Mapped[Player] = relationship()
    team: Mapped["Team | None"] = relationship()


class DeadMoney(Base):
    """A cap charge for a player no longer on the team: the rest of his signing bonus,
    accelerated when he was released, traded, or retired mid-deal."""

    __tablename__ = "dead_money"

    id: Mapped[int] = mapped_column(primary_key=True)
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id", ondelete="CASCADE"),
                                         index=True)
    player_id: Mapped[int] = mapped_column(ForeignKey("players.id", ondelete="CASCADE"))
    year: Mapped[int] = mapped_column(Integer)  # the cap year it counts against
    amount: Mapped[int] = mapped_column(Integer)
    reason: Mapped[str] = mapped_column(String(12))  # released | traded | retired

    player: Mapped[Player] = relationship()


class Season(Base):
    __tablename__ = "seasons"
    __table_args__ = (UniqueConstraint("league_id", "year"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    league_id: Mapped[int] = mapped_column(ForeignKey("leagues.id", ondelete="CASCADE"))
    year: Mapped[int] = mapped_column(Integer)
    # free_agency | draft | preseason | regular_season | playoffs | offseason
    phase: Mapped[str] = mapped_column(String(20), default="preseason")
    current_week: Mapped[int] = mapped_column(Integer, default=1)
    champion_team_id: Mapped[int | None] = mapped_column(
        ForeignKey("teams.id", ondelete="SET NULL"))
    # Free agency market day to play next (phase "free_agency" only).
    free_agency_day: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    # When the pick on the clock went on it (a draft with several managers).
    pick_clock_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # What happened in the offseason before this season (see services/offseason.py).
    # Deferred: read only when the offseason, the market or the draft works on it.
    offseason_log: Mapped[dict | None] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql"), deferred=True)

    league: Mapped[League] = relationship(back_populates="seasons")
    champion: Mapped["Team | None"] = relationship(foreign_keys=[champion_team_id])
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
    stage: Mapped[str] = mapped_column(String(12), default="regular",
                                       server_default="regular")  # regular | playoff
    playoff_round: Mapped[int | None] = mapped_column(Integer)  # 1 = first playoff round
    neutral_site: Mapped[bool] = mapped_column(default=False, server_default="false")
    overtime: Mapped[bool] = mapped_column(default=False, server_default="false")
    # Simulation provenance: replaying `seed` with `sim_version` reproduces `play_log`.
    seed: Mapped[int | None] = mapped_column(BigInteger)
    sim_version: Mapped[str | None] = mapped_column(String(16))
    # Deferred: tens of KB a game, read one game at a time (box score, playback, Coach
    # Mode). Lists of games (standings, schedules, history) never load it.
    play_log: Mapped[list | None] = mapped_column(JSON().with_variant(JSONB(), "postgresql"),
                                                  deferred=True)
    # Older seasons keep only the plays the box score page needs (scores, injuries, the
    # last play) for games that weren't the franchise's or the playoffs' (services/
    # compaction.py); Watch Mode can't play them.
    log_compacted: Mapped[bool] = mapped_column(default=False, server_default=false())

    season: Mapped[Season] = relationship(back_populates="games")
    home_team: Mapped[Team] = relationship(foreign_keys=[home_team_id])
    away_team: Mapped[Team] = relationship(foreign_keys=[away_team_id])


class CoachedGame(Base):
    """A game the user is coaching (Coach Mode): their calls so far, replayed from the
    kickoff by the engine, and both teams as they were at the start, so later roster moves
    don't change a game in progress."""

    __tablename__ = "coached_games"

    id: Mapped[int] = mapped_column(primary_key=True)
    game_id: Mapped[int] = mapped_column(ForeignKey("games.id", ondelete="CASCADE"),
                                         unique=True)
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id", ondelete="CASCADE"))
    side: Mapped[str] = mapped_column(String(4))  # home | away
    calls: Mapped[list] = mapped_column(JSON().with_variant(JSONB(), "postgresql"))
    teams: Mapped[dict] = mapped_column(JSON().with_variant(JSONB(), "postgresql"))
    autopilot: Mapped[bool] = mapped_column(default=False)  # the AI calls the rest
    status: Mapped[str] = mapped_column(String(12), default="in_progress")  # | final
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    game: Mapped[Game] = relationship()


class PlayoffSeed(Base):
    """A team's seed in its conference's bracket, fixed when the regular season ends."""

    __tablename__ = "playoff_seeds"
    __table_args__ = (UniqueConstraint("season_id", "team_id"),
                      UniqueConstraint("season_id", "conference_id", "seed"))

    id: Mapped[int] = mapped_column(primary_key=True)
    season_id: Mapped[int] = mapped_column(ForeignKey("seasons.id", ondelete="CASCADE"),
                                           index=True)
    conference_id: Mapped[int] = mapped_column(ForeignKey("conferences.id", ondelete="CASCADE"))
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id", ondelete="CASCADE"))
    seed: Mapped[int] = mapped_column(Integer)
    division_winner: Mapped[bool] = mapped_column(default=False)

    team: Mapped["Team"] = relationship()


class DraftPick(Base):
    """A team's pick in a year's draft. It exists (and can be traded) before the order is
    known: `season_id` and `number` are set when that draft opens, from where the
    *original* team finished. `team_id` is the current owner; `player_id` is set once the
    pick is made."""

    __tablename__ = "draft_picks"
    __table_args__ = (UniqueConstraint("season_id", "number"),
                      UniqueConstraint("league_id", "year", "round", "original_team_id"))

    id: Mapped[int] = mapped_column(primary_key=True)
    league_id: Mapped[int] = mapped_column(ForeignKey("leagues.id", ondelete="CASCADE"),
                                           index=True)
    year: Mapped[int] = mapped_column(Integer)  # the draft's year
    round: Mapped[int] = mapped_column(Integer)
    original_team_id: Mapped[int] = mapped_column(ForeignKey("teams.id", ondelete="CASCADE"))
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id", ondelete="CASCADE"))
    season_id: Mapped[int | None] = mapped_column(
        ForeignKey("seasons.id", ondelete="CASCADE"), index=True)
    number: Mapped[int | None] = mapped_column(Integer)  # overall pick, 1-based
    player_id: Mapped[int | None] = mapped_column(
        ForeignKey("players.id", ondelete="SET NULL"))

    team: Mapped["Team"] = relationship(foreign_keys=[team_id])
    original_team: Mapped["Team"] = relationship(foreign_keys=[original_team_id])
    player: Mapped["Player | None"] = relationship()


class Trade(Base):
    """A completed trade. `team_id` proposed it (a member's team) to `partner_id` (the AI's,
    or another member's). `sent` / `received` list what moved, from `team_id`'s side:
    [{"kind": "player" | "pick", "id", "label"}]."""

    __tablename__ = "trades"

    id: Mapped[int] = mapped_column(primary_key=True)
    league_id: Mapped[int] = mapped_column(ForeignKey("leagues.id", ondelete="CASCADE"),
                                           index=True)
    season_id: Mapped[int] = mapped_column(ForeignKey("seasons.id", ondelete="CASCADE"))
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id", ondelete="CASCADE"))
    partner_id: Mapped[int] = mapped_column(ForeignKey("teams.id", ondelete="CASCADE"))
    phase: Mapped[str] = mapped_column(String(20))
    week: Mapped[int] = mapped_column(Integer)
    sent: Mapped[list] = mapped_column(JSON().with_variant(JSONB(), "postgresql"))
    received: Mapped[list] = mapped_column(JSON().with_variant(JSONB(), "postgresql"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    team: Mapped["Team"] = relationship(foreign_keys=[team_id])
    partner: Mapped["Team"] = relationship(foreign_keys=[partner_id])


class TradeOffer(Base):
    """A trade one member offers another (services/trade_offers.py): what `from_team_id`
    sends and receives ([{"kind": "player" | "pick", "id"}]). status:
    pending → accepted (done) | rejected | withdrawn | countered (a counter-offer answers it,
    `parent_id`) | expired | invalid (something in it moved) | review (accepted, waiting out
    the commissioner's veto window) → accepted | vetoed."""

    __tablename__ = "trade_offers"

    id: Mapped[int] = mapped_column(primary_key=True)
    league_id: Mapped[int] = mapped_column(ForeignKey("leagues.id", ondelete="CASCADE"),
                                           index=True)
    season_id: Mapped[int] = mapped_column(ForeignKey("seasons.id", ondelete="CASCADE"))
    from_team_id: Mapped[int] = mapped_column(ForeignKey("teams.id", ondelete="CASCADE"))
    to_team_id: Mapped[int] = mapped_column(ForeignKey("teams.id", ondelete="CASCADE"))
    parent_id: Mapped[int | None] = mapped_column(
        ForeignKey("trade_offers.id", ondelete="SET NULL"))
    send: Mapped[list] = mapped_column(JSON().with_variant(JSONB(), "postgresql"))
    receive: Mapped[list] = mapped_column(JSON().with_variant(JSONB(), "postgresql"))
    note: Mapped[str | None] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(12), default="pending", index=True)
    reason: Mapped[str | None] = mapped_column(String(200))  # why it ended, for people
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    review_ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    trade_id: Mapped[int | None] = mapped_column(ForeignKey("trades.id", ondelete="SET NULL"))

    from_team: Mapped["Team"] = relationship(foreign_keys=[from_team_id])
    to_team: Mapped["Team"] = relationship(foreign_keys=[to_team_id])


class FreeAgentOffer(Base):
    """A team's offer to a free agent during the offseason market (services/free_agency.py).
    status: pending | accepted | lost (he signed elsewhere) | expired (market closed)."""

    __tablename__ = "free_agent_offers"

    id: Mapped[int] = mapped_column(primary_key=True)
    season_id: Mapped[int] = mapped_column(ForeignKey("seasons.id", ondelete="CASCADE"),
                                           index=True)
    player_id: Mapped[int] = mapped_column(ForeignKey("players.id", ondelete="CASCADE"))
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id", ondelete="CASCADE"))
    salary: Mapped[int] = mapped_column(Integer)
    years: Mapped[int] = mapped_column(Integer)
    day: Mapped[int] = mapped_column(Integer)  # market day it was made
    status: Mapped[str] = mapped_column(String(10), default="pending")

    team: Mapped["Team"] = relationship()


class PlayerGameStats(Base):
    """One player's box-score line for one game. Columns mirror app.sim.stats.PlayerLine."""

    __tablename__ = "player_game_stats"
    __table_args__ = (UniqueConstraint("game_id", "player_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    game_id: Mapped[int] = mapped_column(ForeignKey("games.id", ondelete="CASCADE"), index=True)
    player_id: Mapped[int] = mapped_column(ForeignKey("players.id", ondelete="CASCADE"),
                                           index=True)
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id", ondelete="CASCADE"))
    pass_att: Mapped[int] = mapped_column(Integer, default=0)
    pass_cmp: Mapped[int] = mapped_column(Integer, default=0)
    pass_yds: Mapped[int] = mapped_column(Integer, default=0)
    pass_td: Mapped[int] = mapped_column(Integer, default=0)
    pass_int: Mapped[int] = mapped_column(Integer, default=0)
    sacked: Mapped[int] = mapped_column(Integer, default=0)
    sack_yds_lost: Mapped[int] = mapped_column(Integer, default=0)
    rush_att: Mapped[int] = mapped_column(Integer, default=0)
    rush_yds: Mapped[int] = mapped_column(Integer, default=0)
    rush_td: Mapped[int] = mapped_column(Integer, default=0)
    rush_long: Mapped[int] = mapped_column(Integer, default=0)
    targets: Mapped[int] = mapped_column(Integer, default=0)
    receptions: Mapped[int] = mapped_column(Integer, default=0)
    rec_yds: Mapped[int] = mapped_column(Integer, default=0)
    rec_td: Mapped[int] = mapped_column(Integer, default=0)
    rec_long: Mapped[int] = mapped_column(Integer, default=0)
    fumbles: Mapped[int] = mapped_column(Integer, default=0)
    fumbles_lost: Mapped[int] = mapped_column(Integer, default=0)
    tackles: Mapped[int] = mapped_column(Integer, default=0)
    sacks: Mapped[int] = mapped_column(Integer, default=0)
    interceptions: Mapped[int] = mapped_column(Integer, default=0)
    int_return_yds: Mapped[int] = mapped_column(Integer, default=0)
    passes_defended: Mapped[int] = mapped_column(Integer, default=0)
    forced_fumbles: Mapped[int] = mapped_column(Integer, default=0)
    fg_att: Mapped[int] = mapped_column(Integer, default=0)
    fg_made: Mapped[int] = mapped_column(Integer, default=0)
    fg_long: Mapped[int] = mapped_column(Integer, default=0)
    xp_att: Mapped[int] = mapped_column(Integer, default=0)
    xp_made: Mapped[int] = mapped_column(Integer, default=0)
    punts: Mapped[int] = mapped_column(Integer, default=0)
    punt_yds: Mapped[int] = mapped_column(Integer, default=0)
    penalties: Mapped[int] = mapped_column(Integer, default=0)
    snaps: Mapped[int] = mapped_column(Integer, default=0, server_default="0")

    player: Mapped["Player"] = relationship()


class TeamGameStats(Base):
    """One team's totals for one game. Columns mirror app.sim.stats.TeamLine."""

    __tablename__ = "team_game_stats"
    __table_args__ = (UniqueConstraint("game_id", "team_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    game_id: Mapped[int] = mapped_column(ForeignKey("games.id", ondelete="CASCADE"), index=True)
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id", ondelete="CASCADE"), index=True)
    points: Mapped[int] = mapped_column(Integer, default=0)
    plays: Mapped[int] = mapped_column(Integer, default=0)
    total_yds: Mapped[int] = mapped_column(Integer, default=0)
    pass_yds: Mapped[int] = mapped_column(Integer, default=0)
    rush_yds: Mapped[int] = mapped_column(Integer, default=0)
    pass_att: Mapped[int] = mapped_column(Integer, default=0)
    pass_cmp: Mapped[int] = mapped_column(Integer, default=0)
    rush_att: Mapped[int] = mapped_column(Integer, default=0)
    first_downs: Mapped[int] = mapped_column(Integer, default=0)
    third_down_att: Mapped[int] = mapped_column(Integer, default=0)
    third_down_conv: Mapped[int] = mapped_column(Integer, default=0)
    turnovers: Mapped[int] = mapped_column(Integer, default=0)
    sacks_allowed: Mapped[int] = mapped_column(Integer, default=0)
    penalties: Mapped[int] = mapped_column(Integer, default=0)
    penalty_yds: Mapped[int] = mapped_column(Integer, default=0)
    punts: Mapped[int] = mapped_column(Integer, default=0)
    fg_att: Mapped[int] = mapped_column(Integer, default=0)
    fg_made: Mapped[int] = mapped_column(Integer, default=0)
    time_of_possession: Mapped[int] = mapped_column(Integer, default=0)


class Franchise(Base):
    """A member's team in a league: which league and which team they run.

    One per member of a league, and one manager per team (docs/design/leagues-with-friends.md).
    """

    __tablename__ = "franchises"
    __table_args__ = (UniqueConstraint("league_id", "user_id", name="uq_franchises_league_user"),
                      UniqueConstraint("league_id", "team_id", name="uq_franchises_league_team"))

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(80))
    league_id: Mapped[int] = mapped_column(ForeignKey("leagues.id", ondelete="CASCADE"))
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id", ondelete="CASCADE"))
    # Whose team it is. (Nullable only for the release before shared leagues.)
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    # The most recently activated franchise is the one the app shows.
    activated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, server_default=func.now())

    league: Mapped[League] = relationship()
    team: Mapped[Team] = relationship()


class LeagueMember(Base):
    """Someone who belongs to a league: a commissioner (runs the league) or a manager (runs
    a team). Their team, if they run one, is their Franchise. Only members see a league."""

    __tablename__ = "league_members"
    __table_args__ = (UniqueConstraint("league_id", "user_id", name="uq_league_members"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    league_id: Mapped[int] = mapped_column(ForeignKey("leagues.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String(16))  # "commissioner" | "manager"
    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    # The step of the season (turns.step_key) the member is ready for: they're ready
    # while it's still the league's current step.
    ready_for: Mapped[str | None] = mapped_column(String(60))
    # Which kinds of notification (services/notifications.py) they also get by email.
    email_kinds: Mapped[list] = mapped_column(JSON().with_variant(JSONB(), "postgresql"),
                                              default=list, server_default="[]")

    user: Mapped[User] = relationship()


class Notification(Base):
    """Something for someone to know (services/notifications.py): their pick, a trade offer,
    the week played. Shown in their inbox; emailed too if they asked for that kind
    (`email`: None, "pending" until the worker sends it, then "sent")."""

    __tablename__ = "notifications"
    __table_args__ = (UniqueConstraint("user_id", "key", name="uq_notifications_user_key"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    league_id: Mapped[int | None] = mapped_column(
        ForeignKey("leagues.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(24))
    title: Mapped[str] = mapped_column(String(120))
    body: Mapped[str] = mapped_column(String(300), default="")
    link: Mapped[str | None] = mapped_column(String(200))  # a page in the app
    key: Mapped[str | None] = mapped_column(String(80))  # (once per key: no repeats)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    email: Mapped[str | None] = mapped_column(String(8), index=True)


class LeagueInvite(Base):
    """An invite link to a league: anyone with it can join while it's open (until it
    expires or is revoked). Only the SHA-256 of its token is stored."""

    __tablename__ = "league_invites"

    id: Mapped[int] = mapped_column(primary_key=True)
    league_id: Mapped[int] = mapped_column(ForeignKey("leagues.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    uses: Mapped[int] = mapped_column(Integer, default=0, server_default="0")


ACTIVE_JOB_STATUSES = ("queued", "running")
ACTIVE_JOB = "status IN ('queued', 'running')"  # (for the partial index)


class Job(Base):
    """A long simulation run in the background by a worker (`app.worker`): what to do, how
    far it's got, and how it ended. One active (queued or running) job per league; while
    there is one, the league's other changes wait."""

    __tablename__ = "jobs"
    __table_args__ = (Index("uq_jobs_active_league", "league_id", unique=True,
                            postgresql_where=text(ACTIVE_JOB), sqlite_where=text(ACTIVE_JOB)),)

    id: Mapped[int] = mapped_column(primary_key=True)
    league_id: Mapped[int] = mapped_column(ForeignKey("leagues.id", ondelete="CASCADE"),
                                           index=True)
    kind: Mapped[str] = mapped_column(String(32))  # see services/jobs.KINDS
    params: Mapped[dict | None] = mapped_column(  # e.g. {"seasons": 5} for sim ahead
        JSON().with_variant(JSONB(), "postgresql"))
    # queued | running | done | failed | cancelled
    status: Mapped[str] = mapped_column(String(12), default="queued", index=True)
    progress: Mapped[int] = mapped_column(Integer, default=0)  # steps done ...
    total: Mapped[int] = mapped_column(Integer, default=1)  # ... of this many
    label: Mapped[str] = mapped_column(String(80), default="Waiting to start")
    cancel_requested: Mapped[bool] = mapped_column(default=False, server_default=false())
    result: Mapped[dict | None] = mapped_column(JSON().with_variant(JSONB(), "postgresql"))
    error: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class TeamGamePlan(Base):
    """A team's saved game plan (the franchise edits its own; teams without one play to a
    plan drawn from their roster, `sim.gameplan.generated`)."""

    __tablename__ = "game_plans"

    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id", ondelete="CASCADE"),
                                         primary_key=True)
    plan: Mapped[dict] = mapped_column(JSON().with_variant(JSONB(), "postgresql"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now,
                                                 onupdate=_now)
