"""Game plans in the database: the franchise's saved plan, and the plan any team plays to
(its saved one, or one drawn from its roster). Design: docs/design/dynasty-mode.md §4."""

from collections.abc import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Player, Team, TeamGamePlan
from app.schemas import GamePlanIn, GamePlanOut, PlanRequirement
from app.services.errors import RosterError
from app.services.teams import load_overrides
from app.sim.gameplan import (
    DEFENSE_CHOICES,
    OFFENSE_CHOICES,
    REQUIRED_DEFENSE,
    REQUIRED_OFFENSE,
    TENDENCIES,
    GamePlan,
    generated,
    validate,
)
from app.sim.teams import build_sim_team, plan_ratings


def saved_plans(db: Session, team_ids: Iterable[int]) -> dict[int, GamePlan]:
    ids = list(team_ids)
    return {row.team_id: GamePlan.from_dict(row.plan) for row in db.scalars(
        select(TeamGamePlan).where(TeamGamePlan.team_id.in_(ids)))} if ids else {}


def suggested(db: Session, team: Team) -> GamePlan:
    """The plan drawn from the team's roster (what it plays to without a saved one)."""
    roster = list(db.scalars(select(Player).where(Player.team_id == team.id)))
    sim = build_sim_team(team.id, team.abbreviation, team.full_name, roster,
                         {p.id: p.ratings.as_dict() for p in roster},
                         load_overrides(db, [team.id])[team.id])
    return generated(plan_ratings(sim))


def plan_view(db: Session, team: Team) -> GamePlanOut:
    saved = saved_plans(db, [team.id]).get(team.id)
    advice = suggested(db, team)
    plan = saved or advice
    return GamePlanOut(
        team_id=team.id, custom=saved is not None,
        offense=sorted(plan.offense) if plan.offense is not None else OFFENSE_CHOICES,
        defense=sorted(plan.defense) if plan.defense is not None else DEFENSE_CHOICES,
        tendencies={name: plan.level(name) for name in TENDENCIES},
        offense_audibles=list(plan.offense_audibles),
        defense_audibles=list(plan.defense_audibles),
        suggested={name: advice.level(name) for name in TENDENCIES},
        offense_choices=OFFENSE_CHOICES, defense_choices=DEFENSE_CHOICES,
        tendency_labels=TENDENCIES,
        required=[PlanRequirement(side=side, label=label, keys=[k for k, _ in options])
                  for side, required in (("offense", REQUIRED_OFFENSE),
                                         ("defense", REQUIRED_DEFENSE))
                  for label, options in required.items()])


def save(db: Session, team: Team, franchise_team_id: int | None, payload: GamePlanIn) -> None:
    if team.id != franchise_team_id:
        raise RosterError("Only your own team's game plan can be changed.", 403)
    plan = GamePlan(offense=frozenset(payload.offense), defense=frozenset(payload.defense),
                    tendencies={k: v for k, v in payload.tendencies.items() if v},
                    offense_audibles=tuple(payload.offense_audibles),
                    defense_audibles=tuple(payload.defense_audibles))
    if errors := validate(plan):
        raise RosterError(" ".join(errors), 422)
    row = db.get(TeamGamePlan, team.id)
    if row is None:
        db.add(TeamGamePlan(team_id=team.id, plan=plan.to_dict()))
    else:
        row.plan = plan.to_dict()
    db.flush()


def reset(db: Session, team: Team, franchise_team_id: int | None) -> None:
    """Back to the plan drawn from the roster."""
    if team.id != franchise_team_id:
        raise RosterError("Only your own team's game plan can be changed.", 403)
    row = db.get(TeamGamePlan, team.id)
    if row is not None:
        db.delete(row)
        db.flush()
