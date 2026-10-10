"""Season simulation: play scheduled games with the engine and persist the results."""

import dataclasses
import hashlib
from collections import defaultdict

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.models import Game, Player, PlayerGameStats, Season, Team, TeamGameStats
from app.schemas import SimulateRequest
from app.services.errors import RosterError
from app.services.teams import load_overrides
from app.sim.engine import SIM_VERSION, simulate_game
from app.sim.stats import box_score
from app.sim.teams import SimTeam, build_sim_team


def season_weeks(db: Session, season_id: int) -> int:
    return db.scalar(select(func.max(Game.week)).where(Game.season_id == season_id)) or 0


def game_seed(league_id: int, year: int, week: int, game_id: int) -> int:
    """Stable per-game seed: the same game always simulates the same way."""
    digest = hashlib.sha256(f"{league_id}:{year}:{week}:{game_id}".encode()).digest()
    return int.from_bytes(digest[:6], "big")


def league_sim_teams(db: Session, league_id: int) -> dict[int, SimTeam]:
    """Every team's current roster and depth chart, snapshotted for the engine."""
    teams = db.scalars(select(Team).where(Team.league_id == league_id)).all()
    players = db.scalars(
        select(Player)
        .where(Player.league_id == league_id, Player.team_id.is_not(None))
        .options(selectinload(Player.ratings))
    ).all()
    rosters: dict[int, list[Player]] = defaultdict(list)
    for player in players:
        rosters[player.team_id].append(player)
    overrides = load_overrides(db, [t.id for t in teams])
    return {
        team.id: build_sim_team(team.id, team.abbreviation, team.full_name, rosters[team.id],
                                {p.id: p.ratings.as_dict() for p in rosters[team.id]},
                                overrides[team.id])
        for team in teams
    }


def play_game(db: Session, game: Game, sim_teams: dict[int, SimTeam], league_id: int,
              year: int) -> None:
    seed = game_seed(league_id, year, game.week, game.id)
    result = simulate_game(sim_teams[game.home_team_id], sim_teams[game.away_team_id], seed)
    game.home_score = result.home_score
    game.away_score = result.away_score
    game.overtime = result.overtime
    game.status = "final"
    game.seed = seed
    game.sim_version = SIM_VERSION
    game.play_log = [play.to_dict() for play in result.plays]

    box = box_score(result)
    team_ids = {"home": game.home_team_id, "away": game.away_team_id}
    for side, line in box.teams.items():
        db.add(TeamGameStats(game_id=game.id, team_id=team_ids[side], **dataclasses.asdict(line)))
    for player_id, line in box.players.items():
        db.add(PlayerGameStats(game_id=game.id, player_id=player_id,
                               team_id=team_ids[box.player_team[player_id]],
                               **dataclasses.asdict(line)))


def simulate(db: Session, season: Season, request: SimulateRequest) -> tuple[int, list[Game]]:
    """Play the next week (or every remaining regular-season week). Returns
    (weeks simulated, games played)."""
    weeks = season_weeks(db, season.id)
    if season.current_week > weeks:
        raise RosterError("The regular season is complete.")
    last_week = season.current_week if request.until == "next_week" else weeks

    first_week = season.current_week
    sim_teams = league_sim_teams(db, season.league_id)
    played: list[Game] = []
    if season.phase == "preseason":
        season.phase = "regular_season"
    for week in range(season.current_week, last_week + 1):
        games = db.scalars(select(Game).where(Game.season_id == season.id, Game.week == week,
                                              Game.status == "scheduled").order_by(Game.id))
        for game in games:
            play_game(db, game, sim_teams, season.league_id, season.year)
            played.append(game)
        season.current_week = week + 1
    db.flush()
    return last_week - first_week + 1, played
