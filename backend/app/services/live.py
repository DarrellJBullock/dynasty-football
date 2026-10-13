"""Playing head-to-head (docs/design/head-to-head-and-commissioner.md §3): a game between two
members' teams, both coaching, when both agree.

One manager offers (`offer`) and the other accepts (`accept`); then each snap waits for
both calls, made blind (`call`; the engine's `replay_both`). An optional call clock has the
AI call for a coach who runs out (`settle_clock`, on every read and the worker's minute).
A game still unfinished when its week is played is finished by the AI from both game plans,
its calls so far standing (`finish_with_ai`, from season._play_week).
"""

from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Game, LiveGame
from app.schemas import LiveStateOut
from app.services.coach import _situation, next_game
from app.services.errors import RosterError
from app.services.games import play_out
from app.services.members import human_team_ids, manager_of
from app.services.notifications import notify_team
from app.services.season import game_seed, league_sim_teams, record_result, refresh_availability
from app.services.serializers import game_out, team_summary
from app.sim.coaching import (
    CoachCall,
    HeadToHeadReplay,
    OutOfStep,
    check_call,
    replay_both,
)
from app.sim.teams import team_from_dict, team_to_dict

CLOCKS = (None, 120, 600, 3600, 86_400)  # the call clocks to choose from (seconds)
SETTLE_LIMIT = 400  # calls the clock can make in one go (a long absence)


def _now() -> datetime:
    return datetime.now(UTC)


def _as_utc(moment: datetime) -> datetime:
    return moment if moment.tzinfo else moment.replace(tzinfo=UTC)  # (SQLite drops it)


def live_game(db: Session, game: Game) -> LiveGame | None:
    return db.scalar(select(LiveGame).where(LiveGame.game_id == game.id))


def side_of(game: Game, team_id: int | None) -> str | None:
    if team_id == game.home_team_id:
        return "home"
    if team_id == game.away_team_id:
        return "away"
    return None


def _other(side: str) -> str:
    return "away" if side == "home" else "home"


def _team_of(game: Game, side: str) -> int:
    return game.home_team_id if side == "home" else game.away_team_id


# ---------- agreeing to play ----------

def offer(db: Session, game: Game, team_id: int | None, clock_seconds: int | None) -> LiveGame:
    """Offer to play this week's game against another member live."""
    side = side_of(game, team_id)
    if side is None:
        raise RosterError("Only the two teams' managers can play this game live.", 403)
    season = game.season
    if not {game.home_team_id, game.away_team_id} <= human_team_ids(db, season.league_id):
        raise RosterError("Live games are between two members' teams: coach this one in "
                          "Coach Mode.")
    if game.status != "scheduled":
        raise RosterError("This game has already been played.")
    upcoming = next_game(db, season, team_id)
    if upcoming is None or upcoming.id != game.id:
        raise RosterError("You can only play your team's game this week live.")
    if clock_seconds not in CLOCKS:
        raise RosterError("Pick one of the call clocks offered.", 422)
    existing = live_game(db, game)
    if existing is not None and existing.status != "declined":
        raise RosterError("This game already has a live offer.")
    if existing is not None:
        db.delete(existing)
        db.flush()
    live = LiveGame(game_id=game.id, proposed_by=team_id, status="proposed",
                    clock_seconds=clock_seconds, calls={"home": [], "away": []},
                    autopilot={"home": False, "away": False})
    db.add(live)
    db.flush()
    other = _team_of(game, _other(side))
    proposer = game.home_team if side == "home" else game.away_team
    notify_team(db, other, "live", f"The {proposer.nickname} want to play this week's game live",
                "Accept and you'll both call every play; decline and it's simulated.",
                f"/games/{game.id}/live", key=f"live-offer:{live.id}")
    return live


def accept(db: Session, game: Game, team_id: int | None) -> LiveGame:
    live = _get(db, game)
    side = side_of(game, team_id)
    if live.status != "proposed":
        raise RosterError(f"This offer is {live.status.replace('_', ' ')}.")
    if side is None or team_id == live.proposed_by:
        raise RosterError("Only the other team's manager can accept.", 403)
    if game.status != "scheduled":
        raise RosterError("This game has already been played.")
    season = game.season
    sim_teams = league_sim_teams(db, season.league_id)
    refresh_availability(db, season.league_id, sim_teams)
    live.teams = {"home": team_to_dict(sim_teams[game.home_team_id]),
                  "away": team_to_dict(sim_teams[game.away_team_id])}
    live.status, live.waiting_since = "in_progress", _now()
    db.flush()
    notify_team(db, live.proposed_by, "live", "Your live game is on",
                "Make your calls: each snap waits for both coaches.",
                f"/games/{game.id}/live", key=f"live-on:{live.id}")
    return live


def decline(db: Session, game: Game, team_id: int | None) -> LiveGame:
    live = _get(db, game)
    if live.status != "proposed":
        raise RosterError(f"This offer is {live.status.replace('_', ' ')}.")
    if side_of(game, team_id) is None:
        raise RosterError("Only the two teams' managers can answer.", 403)
    live.status = "declined"
    db.flush()
    other = live.proposed_by if team_id != live.proposed_by else _team_of(
        game, _other(side_of(game, team_id)))
    notify_team(db, other, "live", "The live game is off",
                "It'll be simulated from both game plans.", f"/games/{game.id}/live",
                key=f"live-off:{live.id}")
    return live


def _get(db: Session, game: Game) -> LiveGame:
    live = live_game(db, game)
    if live is None:
        raise RosterError("Nobody has offered to play this game live.", 404)
    return live


# ---------- playing ----------

def _calls(live: LiveGame, side: str) -> list[CoachCall]:
    return [CoachCall.from_dict(c) for c in (live.calls or {}).get(side, [])]


def _replay(live: LiveGame) -> HeadToHeadReplay:
    game = live.game
    season = game.season
    seed = game_seed(season.league_id, season.year, game.week, game.id)
    try:
        return replay_both(
            team_from_dict(live.teams["home"]), team_from_dict(live.teams["away"]), seed,
            {side: _calls(live, side) for side in ("home", "away")},
            autopilot={side: bool((live.autopilot or {}).get(side)) for side in ("home", "away")},
            playoff=game.stage == "playoff", neutral=game.neutral_site)
    except OutOfStep as exc:
        raise RosterError("This game was started on an older game engine and can't be "
                          "continued.") from exc


def _with(calls: list[dict], new: CoachCall) -> list[dict]:
    """An audible goes onto the snap's call (it's decided at the line); anything else is
    the next call."""
    if new.role == "audible":
        return [*calls[:-1], {**calls[-1], "audible": new.play}]
    return [*calls, new.to_dict()]


def _add(live: LiveGame, side: str, new: CoachCall) -> None:
    calls = dict(live.calls or {})
    calls[side] = _with(calls.get(side, []), new)
    live.calls = calls  # (a new dict, so the JSON column is saved)


def _after(db: Session, live: LiveGame, before: HeadToHeadReplay,
           after: HeadToHeadReplay, by: str | None) -> None:
    """After a call: finish the game, or start the clock on whoever's next and tell them."""
    if after.result is not None:
        _finish(db, live, after)
        return
    if len(after.plays) != len(before.plays) or set(after.needs) != set(before.needs):
        live.waiting_since = _now()
        for side in after.needs:
            if side != by:
                notify_team(db, _team_of(live.game, side), "live", "Your call",
                            f"{live.game.away_team.nickname} at {live.game.home_team.nickname}: "
                            "the snap waits on you.", f"/games/{live.game_id}/live",
                            key=f"live-call:{live.id}:{len(after.plays)}:{side}")
    db.flush()


def call(db: Session, live: LiveGame, side: str, play: str, package: str | None = None,
         timeout: bool = False) -> HeadToHeadReplay:
    """`side`'s call for the snap (or decision) the game waits on."""
    _playing(live)
    settle_clock(db, live)
    before = _replay(live)
    if before.result is not None:
        _finish(db, live, before)
        raise RosterError("This game is over.")
    situation = before.needs.get(side)
    if situation is None:
        raise RosterError("It isn't your call: the game is waiting on the other coach.")
    new = CoachCall(situation.role, play, package, timeout)  # type: ignore[arg-type]
    problem = check_call(new, situation)
    if problem:
        raise RosterError(problem, 422)
    _add(live, side, new)
    after = _replay(live)
    _after(db, live, before, after, side)
    return after


def auto(db: Session, live: LiveGame, side: str, scope: str) -> HeadToHeadReplay:
    """Let the AI call for `side`: the next call, the rest of this drive, or the game."""
    _playing(live)
    before = _replay(live)
    if scope == "game":
        live.autopilot = {**(live.autopilot or {}), side: True}
        after = _replay(live)
        _after(db, live, before, after, side)
        return after
    outcome = before
    first = before.needs.get(side)
    while side in outcome.needs:
        situation = outcome.needs[side]
        if scope == "drive" and first and situation.possession != first.possession:
            break  # the drive (theirs or ours) is over
        _add(live, side, CoachCall(situation.role, situation.suggestion,
                                   situation.suggested_package))
        outcome = _replay(live)
        if scope == "play":
            break
    _after(db, live, before, outcome, side)
    return outcome


def settle_clock(db: Session, live: LiveGame, now: datetime | None = None) -> bool:
    """With a call clock: whoever's call ran out gets the AI's call (repeatedly, for a
    long absence). Returns whether anything was called."""
    if live.status != "in_progress" or not live.clock_seconds or live.waiting_since is None:
        return False
    now = now or _now()
    moved = False
    for _ in range(SETTLE_LIMIT):
        if _as_utc(live.waiting_since) + timedelta(seconds=live.clock_seconds) > now:
            break
        outcome = _replay(live)
        if outcome.result is not None:
            _finish(db, live, outcome)
            break
        for side, situation in outcome.needs.items():
            _add(live, side, CoachCall(situation.role, situation.suggestion,
                                       situation.suggested_package))
        moved = True
        live.waiting_since = _as_utc(live.waiting_since) + timedelta(seconds=live.clock_seconds)
    if moved:
        after = _replay(live)
        if after.result is not None:
            _finish(db, live, after)
    db.flush()
    return moved


def _finish(db: Session, live: LiveGame, outcome: HeadToHeadReplay) -> None:
    if outcome.result is not None and live.status == "in_progress":
        record_result(db, live.game, outcome.result)
        live.status = "final"
        db.flush()


def finish_with_ai(db: Session, live: LiveGame) -> None:
    """The week's deadline: the AI calls the rest for both sides; the calls so far stand."""
    live.autopilot = {"home": True, "away": True}
    _finish(db, live, _replay(live))


def _playing(live: LiveGame) -> None:
    if live.status != "in_progress":
        raise RosterError("This game isn't being played live." if live.status != "final"
                          else "This game is over.")


def live_plays(live: LiveGame) -> list[dict]:
    """The plays of a live game in progress (for the 3D playback)."""
    if live.status != "in_progress":
        return []
    return [p.to_dict() for p in _replay(live).plays]


# ---------- the view ----------

def state(db: Session, live: LiveGame, viewer_team: int | None,
          outcome: HeadToHeadReplay | None = None, before: int | None = None) -> LiveStateOut:
    """The live game as one coach (or a watcher) sees it: never the other side's calls."""
    from app.models import User
    from app.services.members import display_name

    game = live.game
    side = side_of(game, viewer_team)
    abbreviations = {"home": game.home_team.abbreviation, "away": game.away_team.abbreviation}
    if live.status == "in_progress":
        settle_clock(db, live)
    if live.status == "in_progress":
        outcome = outcome or _replay(live)
        _finish(db, live, outcome)
    if live.status == "in_progress" and outcome is not None:
        plays, needs = [p.to_dict() for p in outcome.plays], outcome.needs
    elif live.status in ("final", "settled"):
        plays, needs = game.play_log or [], {}
    else:
        plays, needs = [], {}

    def manager(team_id: int) -> str:
        user_id = manager_of(db, team_id)
        return display_name(db.get(User, user_id)) if user_id else "The AI"

    mine = needs.get(side) if side else None
    waiting = [s for s in needs if s != side]
    deadline = (_as_utc(live.waiting_since) + timedelta(seconds=live.clock_seconds)
                if live.clock_seconds and live.waiting_since and live.status == "in_progress"
                else None)
    return LiveStateOut(
        game=game_out(game), status=live.status, side=side,
        team=team_summary(game.home_team if side == "home" else game.away_team) if side else None,
        proposed_by_you=viewer_team == live.proposed_by,
        managers={"home": manager(game.home_team_id), "away": manager(game.away_team_id)},
        clock_seconds=live.clock_seconds, deadline=deadline,
        autopilot=bool((live.autopilot or {}).get(side)) if side else False,
        situation=_situation(mine, abbreviations) if mine else None,
        waiting_on=[abbreviations[s] for s in waiting],
        plays=[play_out(p, abbreviations) for p in plays],
        new_plays=len(plays) - before if before is not None else 0)
