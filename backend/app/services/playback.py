"""3D playback data: a game's play records, typed, with everyone they reference.

Play logs from SIM_VERSION 1.2 on record each scrimmage play's 22 players. Older games
don't, so their lineups are rebuilt from today's depth charts and marked approximate.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.domain.positions import Position
from app.models import Game, Player, Team
from app.schemas import GamePlayback, Personnel, PlaybackPlay, PlaybackPlayer
from app.services.serializers import game_out
from app.services.teams import load_overrides
from app.sim import resolve
from app.sim.playbook import defense_name, offense_name
from app.sim.playcalls import DefenseCall
from app.sim.teams import REPLACEMENT_RATING, SimTeam, build_sim_team, short_name

SCRIMMAGE = {"run", "pass", "sack", "scramble", "kneel", "penalty"}
ID_KEYS = ("player", "qb", "target", "to", "forced_by", "kicker", "punter", "returner")
DEFENSE_KEYS = {"by", "forced_by", "returner"}


def replacement_position(player_id: int) -> Position:
    """Stand-ins have ids -(1000 + slot × 100 + depth) (app/sim/teams.replacement)."""
    return list(Position)[(-player_id - 1000) // 100]


def _sim_team(db: Session, team: Team) -> SimTeam:
    roster = list(db.scalars(select(Player).where(Player.team_id == team.id)
                             .options(selectinload(Player.ratings))))
    return build_sim_team(team.id, team.abbreviation, team.full_name, roster,
                          {p.id: p.ratings.as_dict() for p in roster},
                          load_overrides(db, [team.id])[team.id])


def _live_plays(db: Session, game: Game) -> list[dict]:
    """A game the user is coaching isn't stored until the final whistle: its plays so far
    come from replaying the calls made."""
    from app.services import coach  # (coach builds on the season services)

    coached = coach.coached_game(db, game)
    return coach.live_plays(coached) if coached and coached.status == "in_progress" else []


def _approximate(offense: SimTeam, defense: SimTeam, play: dict) -> Personnel:
    package = (play.get("defense") or {}).get("package", "base")
    return Personnel(offense=[p.id for p in resolve.offense_lineup(offense)],
                     defense=[p.id for p in resolve.defense_lineup(defense,
                                                                   DefenseCall(package=package))],
                     package=package)


def game_playback(db: Session, game: Game) -> GamePlayback:
    log = game.play_log or _live_plays(db, game)
    sides = {"home": game.home_team, "away": game.away_team}
    by_abbreviation = {t.abbreviation: t for t in sides.values()}
    sim_teams: dict[int, SimTeam] = {}

    plays, team_of, approximate = [], {}, False
    for record in log:
        offense = by_abbreviation[record["offense"]]
        defense = game.away_team if offense.id == game.home_team_id else game.home_team
        personnel = record.get("personnel")
        rebuilt = False
        if personnel is None and record["result"].get("type") in SCRIMMAGE:
            for team in (offense, defense):
                if team.id not in sim_teams:
                    sim_teams[team.id] = _sim_team(db, team)
            personnel = _approximate(sim_teams[offense.id], sim_teams[defense.id], record)
            rebuilt = approximate = True
        lineup = Personnel.model_validate(personnel) if personnel else None
        if lineup:
            team_of.update(dict.fromkeys(lineup.offense, offense.id))
            team_of.update(dict.fromkeys(lineup.defense, defense.id))
        # Anyone not in a lineup (kickers, punters, returners): returners and defenders
        # belong to the defense, everyone else to the team with the ball.
        for event in record["events"]:
            for key, value in event.items():
                ids = value if key == "by" and isinstance(value, list) else [value]
                if key not in (*ID_KEYS, "by"):
                    continue
                for pid in ids:
                    if pid is not None:
                        team_of.setdefault(pid, defense.id if key in DEFENSE_KEYS
                                           else offense.id)
        plays.append(PlaybackPlay(
            n=record["n"], quarter=record["quarter"], clock=record["clock"],
            offense=record["offense"], side=record["side"], down=record["down"],
            distance=record["distance"], ball_on=record["ball_on"], call=record["call"],
            defense=record["defense"], result=record["result"], events=record["events"],
            elapsed=record["elapsed"], score=record["score"], text=record["text"],
            personnel=lineup, approximate=rebuilt, play_name=offense_name(record["call"]),
            defense_name=defense_name(record["defense"])))

    return GamePlayback(game=game_out(game), sim_version=game.sim_version,
                        approximate=approximate, players=_players(db, team_of), plays=plays)


def _players(db: Session, team_of: dict[int, int]) -> list[PlaybackPlayer]:
    real = {p.id: p for p in db.scalars(
        select(Player).where(Player.id.in_([pid for pid in team_of if pid > 0]))
        .options(selectinload(Player.ratings)))}
    out = []
    for pid, team_id in sorted(team_of.items()):
        if pid > 0 and pid in real:
            p = real[pid]
            out.append(PlaybackPlayer(id=pid, name=p.full_name,
                                      short_name=short_name(p.first_name, p.last_name),
                                      number=p.jersey_number, position=p.position,
                                      team_id=team_id, speed=p.ratings.speed,
                                      height_in=p.height_in, weight_lb=p.weight_lb))
        elif pid < 0:
            position = replacement_position(pid).value
            out.append(PlaybackPlayer(id=pid, name=f"Reserve {position}",
                                      short_name=f"Reserve {position}", number=0,
                                      position=position, team_id=team_id,
                                      speed=REPLACEMENT_RATING))
    return out
