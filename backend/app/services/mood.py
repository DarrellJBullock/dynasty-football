"""Players' personalities and moods (docs/design/players-and-storylines.md §3; the rules:
domain/personality.py).

- Traits are made once per player from his own random stream (`ensure_traits`), the first
  time they're needed: the league generator's draws are untouched.
- A mood is worked out when it's asked for, from the base he carried into the season and
  this season so far (his role on the depth chart, the record, his pay, a contract year),
  never stored week by week. Each offseason, part of it carries into the next (`carry_over`).
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain import personality as rules
from app.domain.contracts import market_salary
from app.domain.positions import Position
from app.models import League, Player, Season, Team
from app.schemas import LockerRoomOut, LockerRoomPlayer, PlayerMoodOut
from app.services.serializers import team_summary
from app.services.standings import compute_records
from app.services.teams import current_season, load_overrides, load_roster, team_lineup


def ensure_traits(db: Session, league_id: int) -> None:
    """Every player in the league without traits gets them (from his own stream)."""
    for player in db.scalars(select(Player).where(Player.league_id == league_id,
                                                  Player.drive.is_(None))):
        made = rules.make(rules.rng_for(league_id, player.id), player.age)
        player.drive, player.temperament = made.drive, made.temperament
    db.flush()


def _traits(player: Player) -> rules.Traits:
    return rules.Traits(player.drive or "steady", player.temperament or "team_player")


def _situations(db: Session, season: Season | None, team: Team,
                roster: list[Player]) -> dict[int, rules.Situation]:
    """Each player's season on `team`, as his mood sees it."""
    lineup = team_lineup(roster, load_overrides(db, [team.id])[team.id])
    starters = {p.id for players in lineup.values() for p in players}
    weakest = {pos.value: min(p.overall for p in players)
               for pos, players in lineup.items() if players}
    record = compute_records(db, season, [team.id])[team.id] if season else None
    played = record and record.wins + record.losses + record.ties
    out = {}
    for player in roster:
        if player.id in starters:
            role = "starter"
        elif (player.age >= rules.BENCH_AGE and player.position in weakest
              and player.overall >= weakest[player.position] - rules.BENCH_GAP):
            role = "benched"
        else:
            role = "backup"
        contract = player.active_contract
        price = market_salary(Position(player.position), player.overall)
        out[player.id] = rules.Situation(
            role=role, win_pct=record.win_pct if played else None,
            pay_ratio=contract.salary / price if contract and price else None,
            contract_year=bool(contract and season and contract.end_year <= season.year))
    return out


def _free_agent() -> rules.Situation:
    return rules.Situation(role="free_agent", win_pct=None, pay_ratio=None,
                           contract_year=False)


def _view(player: Player, situation: rules.Situation) -> PlayerMoodOut:
    traits = _traits(player)
    parts = rules.mood_parts(traits, situation)
    value = rules.mood(player.mood_base, parts)
    return PlayerMoodOut(
        player_id=player.id, name=player.full_name, position=player.position,
        overall=player.overall, drive=traits.drive, drive_label=rules.DRIVES[traits.drive][0],
        drive_means=rules.DRIVES[traits.drive][1], temperament=traits.temperament,
        temperament_label=rules.TEMPERAMENTS[traits.temperament][0],
        temperament_means=rules.TEMPERAMENTS[traits.temperament][1],
        base=player.mood_base, parts=parts, mood=value, label=rules.label(value),
        role=situation.role)


def player_mood(db: Session, player: Player) -> PlayerMoodOut:
    ensure_traits(db, player.league_id)
    if player.team_id is None:
        return _view(player, _free_agent())
    team = db.get(Team, player.team_id)
    roster = load_roster(db, team.id)
    season = current_season(db, team.league_id)
    return _view(player, _situations(db, season, team, roster)[player.id])


def locker_room(db: Session, team: Team) -> LockerRoomOut:
    """The team's mood at a glance: the average, how many are happy to miserable, and the
    unhappiest players with what's eating them."""
    ensure_traits(db, team.league_id)
    roster = load_roster(db, team.id)
    season = current_season(db, team.league_id)
    situations = _situations(db, season, team, roster)
    views = [_view(p, situations[p.id]) for p in roster]
    counts = {name: 0 for _, name in rules.LABELS}
    for view in views:
        counts[view.label] += 1
    unhappiest = sorted(views, key=lambda v: (v.mood, v.player_id))[:8]
    return LockerRoomOut(
        team=team_summary(team),
        average=round(sum(v.mood for v in views) / len(views)) if views else rules.START_MOOD,
        counts=counts,
        unhappiest=[LockerRoomPlayer(
            player_id=v.player_id, name=v.name, position=v.position, overall=v.overall,
            mood=v.mood, label=v.label,
            reason=min(v.parts, key=lambda p: p[1])[0] if v.parts and min(
                p[1] for p in v.parts) < 0 else None) for v in unhappiest])


def carry_over(db: Session, league: League) -> None:
    """As the offseason begins: part of each player's mood carries into next season."""
    ensure_traits(db, league.id)
    season = current_season(db, league.id)
    for team in db.scalars(select(Team).where(Team.league_id == league.id)):
        roster = load_roster(db, team.id)
        situations = _situations(db, season, team, roster)
        for player in roster:
            now = rules.mood(player.mood_base, rules.mood_parts(_traits(player),
                                                                 situations[player.id]))
            player.mood_base = rules.next_base(now)
    for player in db.scalars(select(Player).where(
            Player.league_id == league.id, Player.team_id.is_(None),
            Player.retired_year.is_(None), Player.is_prospect.is_(False))):
        player.mood_base = rules.next_base(player.mood_base)
    db.flush()
