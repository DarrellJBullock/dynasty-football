"""Coach Mode (docs/design/coach-mode.md §3, §6): the user coaches their team's next game.

A coached game stores only the user's calls and both teams as they were at the start;
every request replays the engine from the kickoff to the next decision. When the final
whistle blows the result is stored exactly like a simulated game. Its injuries count
with its week, when the rest of the week is simulated.
"""

from typing import Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import CoachedGame, Game, Season
from app.schemas import CoachSituation, CoachStateOut
from app.services.errors import RosterError
from app.services.free_agency import franchise_team_id
from app.services.games import play_out
from app.services.season import (
    _check_franchise_roster,
    game_seed,
    league_sim_teams,
    record_result,
    refresh_availability,
    season_view,
)
from app.services.serializers import game_out, team_summary
from app.sim.coaching import (
    CHOICE_NAMES,
    CoachCall,
    CoachedReplay,
    OutOfStep,
    Situation,
    check_call,
    replay,
)
from app.sim.playbook import DEFENSE_BY_KEY, OFFENSE_BY_KEY
from app.sim.teams import team_from_dict, team_to_dict
from app.sim.text import spot_label

AutoScope = Literal["play", "drive", "game"]


def next_game(db: Session, season: Season) -> Game | None:
    """The franchise's game this week (or this playoff round), if it hasn't been played."""
    team_id = franchise_team_id(db, season.league_id)
    if team_id is None or season.phase in ("offseason", "free_agency", "draft"):
        return None
    stmt = select(Game).where(Game.season_id == season.id, Game.status == "scheduled",
                              (Game.home_team_id == team_id) | (Game.away_team_id == team_id))
    if season.phase == "playoffs":
        return db.scalars(stmt.where(Game.stage == "playoff").order_by(Game.id)).first()
    return db.scalars(stmt.where(Game.stage == "regular", Game.week == season.current_week)
                      .order_by(Game.id)).first()


def coached_game(db: Session, game: Game) -> CoachedGame | None:
    return db.scalar(select(CoachedGame).where(CoachedGame.game_id == game.id))


def start(db: Session, game: Game) -> CoachedGame:
    """Take the headset for the franchise's next game (or pick up where you left off)."""
    existing = coached_game(db, game)
    if existing:
        return existing
    season = game.season
    if game.status != "scheduled":
        raise RosterError("This game has already been played.")
    upcoming = next_game(db, season)
    if upcoming is None or upcoming.id != game.id:
        raise RosterError("You can only coach your team's next game.")
    if season.phase == "preseason":
        _check_franchise_roster(db, season)
    team_id = franchise_team_id(db, season.league_id)
    sim_teams = league_sim_teams(db, season.league_id)
    refresh_availability(db, season.league_id, sim_teams)
    coached = CoachedGame(
        game_id=game.id, team_id=team_id, side="home" if game.home_team_id == team_id else "away",
        calls=[], autopilot=False, status="in_progress",
        teams={"home": team_to_dict(sim_teams[game.home_team_id]),
               "away": team_to_dict(sim_teams[game.away_team_id])})
    db.add(coached)
    db.flush()
    return coached


def _replay(coached: CoachedGame, calls: list[CoachCall] | None = None,
            autopilot: bool | None = None) -> CoachedReplay:
    game = coached.game
    season = game.season
    seed = game_seed(season.league_id, season.year, game.week, game.id)
    if calls is None:
        calls = [CoachCall.from_dict(c) for c in coached.calls]
    try:
        return replay(team_from_dict(coached.teams["home"]), team_from_dict(coached.teams["away"]),
                      seed, coached.side, calls,
                      autopilot=coached.autopilot if autopilot is None else autopilot,
                      playoff=game.stage == "playoff", neutral=game.neutral_site)
    except OutOfStep as exc:
        raise RosterError("This game was started on an older version of the game engine and "
                          "can't be continued. Abandon it to play or simulate it again.") from exc


def live_plays(coached: CoachedGame) -> list[dict]:
    """The plays of a game in progress, up to the next call."""
    return [p.to_dict() for p in _replay(coached).plays]


def _finish(db: Session, coached: CoachedGame, outcome: CoachedReplay) -> None:
    if outcome.result is not None and coached.status == "in_progress":
        record_result(db, coached.game, outcome.result)
        coached.status = "final"
        db.flush()


def state(db: Session, coached: CoachedGame, outcome: CoachedReplay | None = None,
          new_plays: int = 0) -> CoachStateOut:
    """Where the game stands: the next call to make, and every play so far."""
    game = coached.game
    if coached.status == "in_progress":
        outcome = outcome or _replay(coached)
        _finish(db, coached, outcome)
        plays = [p.to_dict() for p in outcome.plays]
        situation = outcome.situation
    else:
        plays, situation = game.play_log or [], None
    abbreviations = {"home": game.home_team.abbreviation, "away": game.away_team.abbreviation}
    team = game.home_team if coached.side == "home" else game.away_team
    return CoachStateOut(
        game=game_out(game), team=team_summary(team), side=coached.side,
        status="in_progress" if coached.status == "in_progress" else "final",
        autopilot=coached.autopilot, calls=len(coached.calls),
        situation=_situation(situation, abbreviations) if situation else None,
        plays=[play_out(p, abbreviations) for p in plays], new_plays=new_plays,
        season=season_view(db, game.season))


def _situation(s: Situation, abbreviations: dict[str, str]) -> CoachSituation:
    offense = abbreviations[s.possession]
    defense = abbreviations["away" if s.possession == "home" else "home"]
    minutes, seconds = divmod(max(0, s.clock), 60)
    plays = DEFENSE_BY_KEY if s.role == "defense" else OFFENSE_BY_KEY
    names = {**{key: p.name for key, p in plays.items()}, **CHOICE_NAMES}
    return CoachSituation(
        role=s.role, quarter=s.quarter, clock=f"{minutes}:{seconds:02d}", seconds=s.clock,
        clock_running=s.clock_running, possession=s.possession, offense=offense, down=s.down,
        distance=s.distance, ball_on=s.ball_on, spot=spot_label(s.ball_on, offense, defense),
        score=s.score, timeouts=s.timeouts, suggestion=s.suggestion,
        suggestion_name=names.get(s.suggestion, s.suggestion),
        suggested_package=s.suggested_package)


def _in_progress(coached: CoachedGame | None) -> CoachedGame:
    if coached is None:
        raise RosterError("You aren't coaching this game.", 404)
    if coached.status != "in_progress":
        raise RosterError("This game is over.")
    return coached


def call(db: Session, coached: CoachedGame | None, play: str, package: str | None = None,
         timeout: bool = False) -> CoachStateOut:
    """Make the next call and play the snap (and anything after it up to the next call)."""
    coached = _in_progress(coached)
    before = _replay(coached)
    if before.situation is None:
        _finish(db, coached, before)
        raise RosterError("This game is over.")
    new = CoachCall(before.situation.role, play, package, timeout)  # type: ignore[arg-type]
    problem = check_call(new, before.situation)
    if problem:
        raise RosterError(problem, 422)
    coached.calls = [*coached.calls, new.to_dict()]
    after = _replay(coached)
    db.flush()
    return state(db, coached, after, new_plays=len(after.plays) - len(before.plays))


def abandon(db: Session, coached: CoachedGame | None) -> None:
    """Stop coaching a game in progress: it's played (or simulated) from the start again."""
    coached = _in_progress(coached)
    db.delete(coached)
    db.flush()


def auto(db: Session, coached: CoachedGame | None, scope: AutoScope) -> CoachStateOut:
    """Let the AI call the next play, the rest of this drive, or the rest of the game."""
    coached = _in_progress(coached)
    before = _replay(coached)
    if scope == "game":
        coached.autopilot = True
        after = _replay(coached)
        db.flush()
        return state(db, coached, after, new_plays=len(after.plays) - len(before.plays))
    outcome = before
    first = before.situation
    while outcome.situation is not None:
        situation = outcome.situation
        if scope == "drive" and first and situation.possession != first.possession:
            break  # the drive (yours or theirs) is over
        coached.calls = [*coached.calls, CoachCall(
            situation.role, situation.suggestion, situation.suggested_package).to_dict()]
        outcome = _replay(coached)
        if scope == "play":
            break
    db.flush()
    return state(db, coached, outcome, new_plays=len(outcome.plays) - len(before.plays))
