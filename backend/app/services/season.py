"""Season simulation: play scheduled games with the engine and persist the results."""

import dataclasses
import hashlib
from collections import defaultdict
from collections.abc import Callable

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.domain.depth_chart import UNAVAILABLE
from app.models import (
    ACTIVE_JOB_STATUSES,
    CoachedGame,
    Game,
    Job,
    Player,
    PlayerGameStats,
    Season,
    Team,
    TeamGameStats,
)
from app.schemas import SeasonOut, SimulateRequest, SimulationResult
from app.services import injuries, playoffs
from app.services.errors import RosterError
from app.services.gameplans import saved_plans
from app.services.serializers import game_out, job_out, season_out, team_summary
from app.services.teams import load_overrides
from app.sim.engine import SIM_VERSION, GameResult, simulate_game
from app.sim.stats import box_score
from app.sim.teams import SimTeam, build_sim_team


def season_weeks(db: Session, season_id: int) -> int:
    """Regular-season weeks (playoff rounds are scheduled after them)."""
    return playoffs.regular_week_count(db, season_id)


def season_view(db: Session, season: Season) -> SeasonOut:
    """SeasonOut with playoff context (next round name, champion)."""
    out = season_out(season, season_weeks(db, season.id))
    if season.phase == "playoffs":
        upcoming = playoffs.next_round_games(db, season)
        if upcoming:
            out.next_round = playoffs.round_name(db, season, upcoming[0].playoff_round)
    if season.champion_team_id:
        out.champion = team_summary(db.get(Team, season.champion_team_id))
    job = active_job(db, season.league_id)
    if job is not None:
        out.active_job = job_out(job)
    return out


def active_job(db: Session, league_id: int) -> Job | None:
    """The league's queued or running background job, if any."""
    return db.scalar(select(Job).where(Job.league_id == league_id,
                                     Job.status.in_(ACTIVE_JOB_STATUSES)))


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
    plans = saved_plans(db, [t.id for t in teams])
    return {
        team.id: build_sim_team(team.id, team.abbreviation, team.full_name, rosters[team.id],
                                {p.id: p.ratings.as_dict() for p in rosters[team.id]},
                                overrides[team.id], plans.get(team.id))
        for team in teams
    }


def play_game(db: Session, game: Game, sim_teams: dict[int, SimTeam], league_id: int,
              year: int) -> list[dict]:
    """Simulate and store one game; returns its injury events."""
    seed = game_seed(league_id, year, game.week, game.id)
    result = simulate_game(sim_teams[game.home_team_id], sim_teams[game.away_team_id], seed,
                           playoff=game.stage == "playoff", neutral=game.neutral_site)
    record_result(db, game, result)
    return result.injuries


def record_result(db: Session, game: Game, result: GameResult) -> None:
    """Store a finished game: score, play log, and the box score derived from it."""
    game.home_score = result.home_score
    game.away_score = result.away_score
    game.overtime = result.overtime
    game.status = "final"
    game.seed = result.seed
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


def refresh_availability(db: Session, league_id: int, sim_teams: dict[int, SimTeam]) -> None:
    """Re-read who is Out / IR (injuries change week to week; rosters don't mid-sim)."""
    rows = db.execute(select(Player.id, Player.team_id).where(
        Player.league_id == league_id, Player.team_id.is_not(None),
        Player.injury_status.in_(UNAVAILABLE))).all()
    for team in sim_teams.values():
        team.unavailable = set()
    for player_id, team_id in rows:
        sim_teams[team_id].unavailable.add(player_id)


def _play_week(db: Session, season: Season, games: list[Game], sim_teams: dict[int, SimTeam],
               stage: str, week: int | None = None) -> None:
    """Play one week (or playoff round) with this week's lineups, then update injuries:
    players hurt this week miss the coming weeks, earlier injuries count down. A game the
    user coached to the end is already played; its injuries count with its week."""
    # A live game (head-to-head) not finished by now: the AI finishes it from both game
    # plans, the calls so far standing (services/live.py).
    from app.models import LiveGame
    from app.services import live

    for unfinished in db.scalars(select(LiveGame).where(
            LiveGame.game_id.in_([g.id for g in games]),
            LiveGame.status == "in_progress")).all():
        live.finish_with_ai(db, unfinished)
    games = [g for g in games if g.status == "scheduled"]
    in_progress = db.scalar(select(CoachedGame).where(
        CoachedGame.game_id.in_([g.id for g in games]), CoachedGame.status == "in_progress"))
    if in_progress:
        raise RosterError("Finish the game you're coaching (or let the AI finish it) before "
                          "simulating the week.")
    coached = [c for c in db.scalars(select(CoachedGame).join(Game).where(
        Game.season_id == season.id, Game.stage == stage, CoachedGame.status == "final"))
        if stage == "playoff" or c.game.week == week]
    played_live = [g for g in db.scalars(select(LiveGame).join(Game).where(
        Game.season_id == season.id, Game.stage == stage, LiveGame.status == "final"))
        if stage == "playoff" or g.game.week == week]
    hurt = [e for c in [*coached, *played_live] for play in c.game.play_log or []
            for e in play["events"] if e["t"] == "injury"]
    for c in [*coached, *played_live]:
        c.status = "settled"
    refresh_availability(db, season.league_id, sim_teams)
    hurt += [e for game in games
             for e in play_game(db, game, sim_teams, season.league_id, season.year)]
    db.flush()
    injuries.after_week(db, season.league_id, hurt)


def _check_franchise_roster(db: Session, season: Season) -> None:
    """Every team a member runs must be down to 53 (the draft can take it over) before
    week 1."""
    from app.domain.positions import ROSTER_MAX
    from app.models import Team
    from app.services.members import human_team_ids

    for team_id in sorted(human_team_ids(db, season.league_id)):
        count = db.scalar(select(func.count(Player.id)).where(Player.team_id == team_id)) or 0
        if count > ROSTER_MAX:
            team = db.get(Team, team_id)
            raise RosterError(f"The {team.full_name} must cut to {ROSTER_MAX} (they have "
                              f"{count}) before the season starts.")


# Called after each week or round with its label and whether more are to come (a background
# job records its progress there, and may stop the run between weeks).
OnStep = Callable[[str, bool], None]


def simulate(db: Session, season: Season, request: SimulateRequest,
             on_step: OnStep | None = None) -> tuple[int, list[Game]]:
    """Play the next week (or playoff round), the rest of the regular season, or the rest of
    the playoffs. Returns (weeks/rounds simulated, games played)."""
    weeks = season_weeks(db, season.id)
    regular_done = season.current_week > weeks
    if season.phase == "offseason":
        raise RosterError("The season is complete.")
    if season.phase == "free_agency":
        raise RosterError("Finish free agency before the season starts.")
    if season.phase == "draft":
        raise RosterError("Finish the draft before the season starts.")
    if season.phase == "preseason":
        _check_franchise_roster(db, season)
    if request.until == "end_of_regular_season" and regular_done:
        raise RosterError("The regular season is complete.")
    if request.until == "end_of_playoffs" and not regular_done:
        raise RosterError("Finish the regular season before simming the playoffs.")

    sim_teams = league_sim_teams(db, season.league_id)
    played: list[Game] = []
    steps = 0
    if not regular_done:
        last_week = season.current_week if request.until == "next_week" else weeks
        if season.phase == "preseason":
            season.phase = "regular_season"
        for week in range(season.current_week, last_week + 1):
            games = list(db.scalars(select(Game).where(
                Game.season_id == season.id, Game.week == week, Game.stage == "regular",
                Game.status == "scheduled").order_by(Game.id)))
            _play_week(db, season, games, sim_teams, "regular", week)
            played += games
            season.current_week = week + 1
            steps += 1
            if on_step:
                on_step(f"Week {week} of {weeks}", week < last_week)
        db.flush()
        if season.current_week > weeks:
            playoffs.start(db, season)
        return steps, played

    while season.phase == "playoffs":
        games = playoffs.next_round_games(db, season)
        name = playoffs.round_name(db, season, games[0].playoff_round) if games else "Playoffs"
        _play_week(db, season, games, sim_teams, "playoff")
        played += games
        playoffs.finish_round(db, season)
        steps += 1
        if season.champion_team_id:
            from app.services.history import award_season  # (it builds on this module)

            award_season(db, season)
            from app.services.staff import record_season  # (it builds on this module)

            record_season(db, season)
        if request.until == "next_week":
            break
        if on_step:
            on_step(name, season.phase == "playoffs")
    return steps, played


def simulation_result(db: Session, season: Season, steps: int, played: list[Game],
                      team_id: int | None = None) -> SimulationResult:
    """What a sim did, with `team_id`'s games (the viewer's) among those played."""
    return SimulationResult(
        weeks_simulated=steps, games_simulated=len(played), season=season_view(db, season),
        franchise_games=[game_out(g) for g in played
                         if team_id in (g.home_team_id, g.away_team_id)])
