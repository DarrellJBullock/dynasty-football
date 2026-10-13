"""The League log (docs/design/head-to-head-and-commissioner.md §4): every edit to a player
or team, and every commissioner action (vetoes, settings, members), for every member to see.

Also the commissioner's edits that the roster editor doesn't make: moving a player to
another team (or free agency), and rewriting his contract.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.contracts import MIN_SALARY
from app.domain.positions import available_jersey
from app.models import Contract, LeagueLogEntry, Player, Team, User
from app.schemas import LeagueLogEntryOut, LeagueLogOut
from app.services import cap
from app.services.depth_chart import remove_player
from app.services.errors import RosterError
from app.services.members import display_name
from app.services.retired import retired_numbers
from app.services.teams import current_season, load_roster

ACTIONS = ("player", "new_player", "move", "contract", "team", "import", "veto", "approve",
           "settings", "member", "reverse", "rollback",
           "rules")
PAGE = 50

# What an edit can change about a player, as the log shows it.
_PLAYER_FIELDS = ("first_name", "last_name", "position", "jersey_number", "age", "height_in",
                  "weight_lb", "college", "potential", "development_trait", "injury_status")
_TEAM_FIELDS = ("city", "nickname", "abbreviation", "primary_color", "secondary_color",
                "stadium")


def record(db: Session, league_id: int, user: User | None, action: str, summary: str,
           changes: list[dict] | None = None, team_id: int | None = None,
           player_id: int | None = None) -> LeagueLogEntry:
    if action not in ACTIONS:
        raise ValueError(f"unknown log action {action!r}")
    entry = LeagueLogEntry(league_id=league_id, user_id=user.id if user else None,
                           actor=display_name(user) if user else "The league",
                           action=action, summary=summary[:300], changes=changes or [],
                           team_id=team_id, player_id=player_id)
    db.add(entry)
    db.flush()
    return entry


def diff(before: dict, after: dict) -> list[dict]:
    """[{field, before, after}] for every field that changed."""
    return [{"field": key, "before": before.get(key), "after": after.get(key)}
            for key in after if before.get(key) != after.get(key)]


def player_fields(player: Player) -> dict:
    """A player as an edit sees him: his bio, then each rating."""
    fields = {f: getattr(player, f) for f in _PLAYER_FIELDS}
    fields.update(player.ratings.as_dict())
    return fields


def team_fields(team: Team) -> dict:
    return {f: getattr(team, f) for f in _TEAM_FIELDS}


def _team_name(db: Session, team_id: int | None) -> str:
    return db.get(Team, team_id).full_name if team_id else "free agency"


# ---------- the commissioner's edits ----------

def move_player(db: Session, player: Player, team_id: int | None) -> tuple[str, str]:
    """Move a player to another team (keeping his contract, with no dead money) or to free
    agency (his contract ends, with no dead money). Returns (from, to) team names."""
    if player.retired_year is not None:
        raise RosterError("A retired player can't be moved.")
    if team_id == player.team_id:
        raise RosterError("He's already there.")
    if team_id is not None:
        team = db.get(Team, team_id)
        if team is None or team.league_id != player.league_id:
            raise RosterError("Team not found.", 404)
        roster = load_roster(db, team_id)
        if len(roster) >= team.league.roster_max:
            raise RosterError(f"{team.full_name}'s roster is full ({team.league.roster_max} "
                              "players).")
    old = _team_name(db, player.team_id)
    season = current_season(db, player.league_id)
    year = cap.cap_year(season) if season else 0
    contract = player.active_contract
    remove_player(db, player)
    if contract is not None:
        contract.is_active = False
    if team_id is None:
        player.team_id = None
    else:
        taken = {p.jersey_number for p in roster} | retired_numbers(db, team_id)
        if player.jersey_number in taken:
            player.jersey_number = available_jersey(player.position, taken)
        player.team_id = team_id
        remaining = contract.end_year - year + 1 if contract is not None else 0
        player.contracts.append(Contract(
            team_id=team_id, start_year=year, years=max(remaining, 1),
            salary=contract.salary if contract is not None else MIN_SALARY, signing_bonus=0))
    db.flush()
    return old, _team_name(db, team_id)


def set_contract(db: Session, player: Player, salary: int, years: int) -> tuple[dict, dict]:
    """Rewrite a player's contract: `salary` a season for `years` seasons from this one (its
    bonus as for any new deal). Returns his contract before and after."""
    if player.team_id is None:
        raise RosterError("A free agent has no contract to change.")
    season = current_season(db, player.league_id)
    if season is None:
        raise RosterError("The league has no season.", 404)
    old = player.active_contract
    before = _contract_fields(old)
    if old is not None:
        old.is_active = False
    new = Contract.signed(player.team_id, cap.cap_year(season), years, salary)
    player.contracts.append(new)
    db.flush()
    return before, _contract_fields(new)


def _contract_fields(contract: Contract | None) -> dict:
    if contract is None:
        return {"salary": None, "years": None, "end_year": None}
    return {"salary": contract.salary, "years": contract.years, "end_year": contract.end_year}


# ---------- the view ----------

def entries(db: Session, league_id: int, before: int | None = None,
            action: str | None = None) -> LeagueLogOut:
    """The newest entries first, a page at a time (`before`: an entry id)."""
    query = select(LeagueLogEntry).where(LeagueLogEntry.league_id == league_id)
    if before is not None:
        query = query.where(LeagueLogEntry.id < before)
    if action is not None:
        query = query.where(LeagueLogEntry.action == action)
    rows = db.scalars(query.order_by(LeagueLogEntry.id.desc()).limit(PAGE + 1)).all()
    return LeagueLogOut(
        entries=[LeagueLogEntryOut(
            id=e.id, created_at=e.created_at, actor=e.actor, action=e.action,
            summary=e.summary, team_id=e.team_id, player_id=e.player_id,
            changes=e.changes or []) for e in rows[:PAGE]],
        more=len(rows) > PAGE)
