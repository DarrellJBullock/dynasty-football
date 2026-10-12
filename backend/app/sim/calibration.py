"""League-wide output metrics, checked against the targets in the design doc (§7).

    metrics = measure(teams, games=300, seed=1)

Used by tests/test_sim_calibration.py and handy when tuning `Tuning` values by hand:
    python -m app.sim.calibration
"""

import random
from collections.abc import Sequence
from dataclasses import dataclass

from app.sim.engine import GameResult, simulate_game
from app.sim.stats import box_score
from app.sim.teams import SimTeam
from app.sim.tuning import DEFAULT_TUNING, Tuning

# Per team per game unless noted. (low, high) inclusive.
TARGETS: dict[str, tuple[float, float]] = {
    "points": (20, 25),
    "plays": (60, 68),
    "completion_pct": (60, 67),
    "net_yards_per_dropback": (5.8, 7.0),  # passing yards minus sack yards, per dropback
    "yards_per_carry": (4.0, 4.6),
    "sacks_allowed": (1.8, 2.8),
    "interception_pct": (1.8, 2.8),
    "fumbles_lost": (0.4, 0.8),
    "field_goal_pct": (82, 90),
    "punts": (3.5, 5.0),
    "third_down_pct": (35, 44),
    "touchdowns": (2.0, 2.9),
    "tie_pct": (0, 1.5),  # of games (one tie in 400 games = 0.25%)
    "penalties": (5.0, 7.0),  # accepted
    "penalty_yards": (40, 60),
}


@dataclass
class Metrics:
    values: dict[str, float]
    games: list[GameResult]

    def out_of_range(self) -> dict[str, tuple[float, tuple[float, float]]]:
        return {k: (v, TARGETS[k]) for k, v in self.values.items()
                if k in TARGETS and not TARGETS[k][0] <= v <= TARGETS[k][1]}

    def report(self) -> str:
        lines = []
        for key, value in self.values.items():
            low, high = TARGETS.get(key, (None, None))
            flag = "" if low is None or low <= value <= high else "  <-- out of range"
            target = f"[{low}-{high}]" if low is not None else ""
            lines.append(f"{key:>20}: {value:7.2f} {target}{flag}")
        return "\n".join(lines)


def measure(teams: Sequence[SimTeam], games: int, seed: int = 1,
            tuning: Tuning = DEFAULT_TUNING) -> Metrics:
    rng = random.Random(seed)
    results = []
    for i in range(games):
        home, away = rng.sample(list(teams), 2)
        results.append(simulate_game(home, away, seed=seed * 100_003 + i, tuning=tuning))

    totals: dict[str, float] = {}

    def add(key: str, value: float) -> None:
        totals[key] = totals.get(key, 0) + value

    rushers_fumbles = 0
    for game in results:
        box = box_score(game)
        for team in box.teams.values():
            for key in ("points", "plays", "pass_att", "pass_cmp", "pass_yds", "rush_att",
                        "rush_yds", "sacks_allowed", "punts", "fg_att", "fg_made", "turnovers",
                        "third_down_att", "third_down_conv", "penalties", "penalty_yds"):
                add(key, getattr(team, key))
        add("interceptions", sum(p.pass_int for p in box.players.values()))
        rushers_fumbles += sum(p.fumbles_lost for p in box.players.values())
        add("touchdowns", sum(1 for play in game.plays
                              if play.result.get("touchdown") or play.result.get("defensive_td")))
        add("ties", int(game.home_score == game.away_score))
        add("home_wins", int(game.home_score > game.away_score))
        add("overtime", int(game.overtime))

    team_games = 2 * len(results)
    dropbacks = totals["pass_att"] + totals["sacks_allowed"]
    values = {
        "points": totals["points"] / team_games,
        "plays": totals["plays"] / team_games,
        "completion_pct": 100 * totals["pass_cmp"] / totals["pass_att"],
        "net_yards_per_dropback": totals["pass_yds"] / dropbacks,
        "yards_per_carry": totals["rush_yds"] / totals["rush_att"],
        "sacks_allowed": totals["sacks_allowed"] / team_games,
        "interception_pct": 100 * totals["interceptions"] / totals["pass_att"],
        "fumbles_lost": rushers_fumbles / team_games,
        "field_goal_pct": 100 * totals["fg_made"] / max(1, totals["fg_att"]),
        "punts": totals["punts"] / team_games,
        "third_down_pct": 100 * totals["third_down_conv"] / max(1, totals["third_down_att"]),
        "touchdowns": totals["touchdowns"] / team_games,
        "tie_pct": 100 * totals["ties"] / len(results),
        "penalties": totals["penalties"] / team_games,
        "penalty_yards": totals["penalty_yds"] / team_games,
        "home_win_pct": 100 * totals["home_wins"] / len(results),
        "overtime_pct": 100 * totals["overtime"] / len(results),
        "pass_rate": 100 * totals["pass_att"] / (totals["pass_att"] + totals["rush_att"]),
    }
    return Metrics(values, results)


def default_league_teams(seed: int = 2026) -> list[SimTeam]:
    """The shipped league as SimTeams, built in an in-memory database."""
    from sqlalchemy import create_engine, select
    from sqlalchemy.orm import Session

    from app.db import Base
    from app.models import Team
    from app.seed.generator import generate_league
    from app.sim.teams import build_sim_team

    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        generate_league(session, seed=seed)
        session.flush()
        teams = []
        for team in session.scalars(select(Team).order_by(Team.id)):
            roster = list(team.players)
            teams.append(build_sim_team(team.id, team.abbreviation, team.full_name, roster,
                                        {p.id: p.ratings.as_dict() for p in roster}))
    engine.dispose()
    return teams


if __name__ == "__main__":
    print(measure(default_league_teams(), games=400).report())
