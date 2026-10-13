"""League parity over many seasons (docs/design/owners-and-front-offices.md §6): do the AI
front offices keep a league competitive, or does it drift into a few dynasties and a
permanent basement? Plays the sample league season after season (every team, the
franchise too, on autopilot, as sim ahead does) in an in-memory database, and checks:

- the spread of regular-season records each season (the standard deviation of win
  percentage; real leagues sit near 0.19), within `SPREAD`;
- how many different teams win titles, at least `CHAMPIONS_SHARE` of the seasons played;
- how long the best and worst teams stay there (the longest run of seasons the same team
  has the best, or the worst, record), at most `STREAK`.

    python -m app.parity --seasons 20
"""

import argparse
import statistics
import sys
from dataclasses import dataclass

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

SPREAD = (0.12, 0.24)
CHAMPIONS_SHARE = 1 / 3
STREAK = 5


@dataclass(frozen=True)
class SeasonResult:
    year: int
    win_pcts: dict[int, float]  # team id -> regular-season win percentage
    champion: int


@dataclass(frozen=True)
class Summary:
    seasons: int
    spread: float  # mean of each season's standard deviation of win percentage
    champions: int  # different champions
    best_streak: int  # longest run of seasons the same team had the best record
    worst_streak: int  # ...and the worst
    problems: list[str]


def _streak(leaders: list[int]) -> int:
    longest = run = 0
    previous = None
    for team in leaders:
        run = run + 1 if team == previous else 1
        longest, previous = max(longest, run), team
    return longest


def summarize(results: list[SeasonResult]) -> Summary:
    spreads = [statistics.pstdev(r.win_pcts.values()) for r in results]
    best = [max(r.win_pcts, key=lambda t: (r.win_pcts[t], -t)) for r in results]
    worst = [min(r.win_pcts, key=lambda t: (r.win_pcts[t], t)) for r in results]
    spread = statistics.mean(spreads) if spreads else 0.0
    champions = len({r.champion for r in results})
    problems = []
    if not SPREAD[0] <= spread <= SPREAD[1]:
        problems.append(f"records spread {spread:.3f}, outside {SPREAD[0]}-{SPREAD[1]}")
    if results and champions < len(results) * CHAMPIONS_SHARE:
        problems.append(f"only {champions} different champions in {len(results)} seasons")
    for name, streak in (("best", _streak(best)), ("worst", _streak(worst))):
        if streak > STREAK:
            problems.append(f"the same team had the {name} record {streak} seasons running")
    return Summary(len(results), round(spread, 3), champions, _streak(best), _streak(worst),
                   problems)


def play(seasons: int, seed: int = 2026, report=print) -> list[SeasonResult]:
    """Play `seasons` seasons of the sample league, every team on autopilot."""
    from app.models import Base, Season
    from app.schemas import SimulateRequest
    from app.seed.generator import generate_league
    from app.services import draft, free_agency, offseason
    from app.services import season as season_service
    from app.services.standings import compute_records
    from app.services.teams import current_season

    engine = create_engine("sqlite://", connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    Base.metadata.create_all(engine)
    results = []
    with Session(engine) as db:
        league = generate_league(db, seed=seed)
        league.firing = "off"  # (nobody to choose a new job)
        db.commit()
        team_ids = [t.id for t in league.teams]
        while len(results) < seasons:
            season = current_season(db, league.id)
            season_service.simulate(db, season, SimulateRequest(until="end_of_regular_season"))
            season_service.simulate(db, season, SimulateRequest(until="end_of_playoffs"))
            records = compute_records(db, season, team_ids)
            results.append(SeasonResult(season.year, {t: r.win_pct for t, r in records.items()},
                                        season.champion_team_id))
            report(f"{season.year}: champion {season.champion_team_id}, spread "
                   f"{statistics.pstdev(results[-1].win_pcts.values()):.3f}")
            new = offseason.advance(db, season, autopilot=True)
            free_agency.play_days(db, new, "end", autopilot=True)
            draft.draft_view(db, league)
            draft.play(db, new, "end", autopilot=True)
            db.commit()
            assert db.scalar(select(Season.id).where(Season.id == new.id))
    return results


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m app.parity")
    parser.add_argument("--seasons", type=int, default=20)
    parser.add_argument("--seed", type=int, default=2026)
    args = parser.parse_args()
    summary = summarize(play(args.seasons, args.seed))
    print(f"\n{summary.seasons} seasons: records spread {summary.spread} (target "
          f"{SPREAD[0]}-{SPREAD[1]}), {summary.champions} different champions, the best "
          f"record held {summary.best_streak} seasons running at most, the worst "
          f"{summary.worst_streak}")
    for problem in summary.problems:
        print(f"PROBLEM: {problem}")
    sys.exit(1 if summary.problems else 0)


if __name__ == "__main__":
    main()
