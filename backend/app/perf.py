"""Read performance: `python -m app.perf build` makes a league with seasons played in the
database at DATABASE_URL (wiping it), and `python -m app.perf measure` times every API
read for its franchise and counts its database queries.

    python -m app.perf build --seasons 3
    python -m app.perf measure --runs 7 [--budget-ms 300] [--max-queries 40]

With budgets, `measure` exits non-zero if any read's 95th percentile or query count is
over (CI runs it that way). Design: docs/design/platform.md §7.
"""

import argparse
import logging
import re
import statistics
import sys
import time
from contextlib import contextmanager

from fastapi.testclient import TestClient
from sqlalchemy import event, select

from app.api.access import SESSION_COOKIE
from app.db import SessionLocal, engine
from app.main import create_app
from app.models import Franchise, Game, League, Player, PlayerGameStats, Season, User
from app.schemas import SimulateRequest
from app.seed.generator import clear_database, generate_league
from app.services import accounts, draft, free_agency, offseason, sharing
from app.services import season as season_service
from app.services.members import give_league
from app.services.teams import current_season

EMAIL, PASSWORD = "perf@example.test", "perf-password"


def build(seasons: int) -> None:
    """A fresh league with `seasons` full seasons played and the next one half done."""
    with SessionLocal() as db:
        clear_database(db)
        league = generate_league(db, seed=2026)
        give_league(db, league, accounts.sign_up(db, EMAIL, PASSWORD))
        db.commit()
        franchise = db.scalar(select(Franchise).where(Franchise.league_id == league.id))
        for number in range(seasons + 1):
            season = current_season(db, league.id)
            if number == seasons:  # the current season: half of it played
                for _ in range(season_service.season_weeks(db, season.id) // 2):
                    season_service.simulate(db, season, SimulateRequest(until="next_week"))
                db.commit()
                break
            season_service.simulate(db, season, SimulateRequest(until="end_of_regular_season"))
            season_service.simulate(db, season, SimulateRequest(until="end_of_playoffs"))
            db.commit()
            new = offseason.advance(db, season)
            free_agency.play_days(db, new, "end")
            draft.draft_view(db, league)  # (generates the class)
            draft.play(db, new, "end")
            draft.cut_down(db, franchise.team)
            db.commit()
            print(f"played {season.year}", flush=True)


@contextmanager
def counting():
    """Count the SQL statements run inside the block."""
    count = [0]

    def before(*_args):
        count[0] += 1

    event.listen(engine, "before_cursor_execute", before)
    try:
        yield count
    finally:
        event.remove(engine, "before_cursor_execute", before)


def reads(client: TestClient) -> dict[str, str]:
    """Every GET route, filled in with this franchise's ids: {template: url}."""
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.email == EMAIL))
        league = db.scalar(select(League).where(League.user_id == user.id))
        franchise = db.scalar(select(Franchise).where(Franchise.league_id == league.id))
        season = db.scalar(select(Season).where(Season.league_id == league.id)
                           .order_by(Season.year.desc()))
        first_year = max(season.year - 10, db.scalar(
            select(Season.year).where(Season.league_id == league.id).order_by(Season.year)))
        game = db.scalar(select(Game).where(Game.status == "final").order_by(Game.id.desc()))
        # A veteran with a few seasons of stats.
        player = db.scalar(select(PlayerGameStats.player_id)
                           .join(Player, Player.id == PlayerGameStats.player_id)
                           .where(Player.team_id == franchise.team_id)
                           .group_by(PlayerGameStats.player_id)
                           .order_by(PlayerGameStats.player_id).limit(1))
        token = sharing.create_link(db, league)  # (the public link's reads are timed too)
        db.commit()
    ids = {"league_id": league.id, "season_id": season.id, "team_id": franchise.team_id,
           "player_id": player, "game_id": game.id, "franchise_id": franchise.id,
           "slot": "QB", "fmt": "csv", "token": token}
    urls = {}
    for path, methods in client.app.openapi()["paths"].items():
        names = re.findall(r"{(\w+)}", path)
        # (no job to read, health isn't a read, and Coach Mode and a live game read a game
        # being coached)
        if ("get" not in methods or "job_id" in names
                or path.endswith(("/health", "/ready", "/coach", "/live"))):
            continue
        urls[path] = re.sub(r"{(\w+)}", lambda m: str(ids[m.group(1)]), path)
        if path.endswith("/dynasty"):  # (every season played, as a Dynasty report)
            urls[path] += f"?from_year={first_year}&to_year={season.year - 1}"
    return urls


def measure(runs: int, budget_ms: float | None, max_queries: int | None) -> int:
    for name in ("app.request", "httpx"):  # (a line per request would bury the table)
        logging.getLogger(name).setLevel(logging.WARNING)
    app = create_app()
    over = 0
    with TestClient(app) as client:
        with SessionLocal() as db:
            user = db.scalar(select(User).where(User.email == EMAIL))
            client.cookies.set(SESSION_COOKIE, accounts.start_session(db, user))
            db.commit()
        rows = []
        for template, url in reads(client).items():
            times, queries, status = [], 0, None
            for run in range(runs + 1):
                with counting() as count:
                    started = time.perf_counter()
                    status = client.get(url).status_code
                    elapsed = (time.perf_counter() - started) * 1000
                if run:  # (the first run warms caches)
                    times.append(elapsed)
                    queries = count[0]
            p95 = sorted(times)[max(0, round(0.95 * len(times)) - 1)]
            rows.append((p95, statistics.median(times), queries, status, template))
        print(f"{'p95 ms':>8} {'p50 ms':>8} {'queries':>8} {'status':>6}  route")
        for p95, p50, queries, status, template in sorted(rows, reverse=True):
            flags = []
            if budget_ms and p95 > budget_ms:
                flags.append("SLOW")
            if max_queries and queries > max_queries:
                flags.append("QUERIES")
            if status != 200:
                flags.append(f"HTTP {status}")
            over += bool(flags)
            print(f"{p95:8.1f} {p50:8.1f} {queries:8d} {status:6d}  {template}"
                  + (f"  <- {', '.join(flags)}" if flags else ""))
    return over


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m app.perf")
    commands = parser.add_subparsers(dest="command", required=True)
    build_cmd = commands.add_parser("build", help="wipe the database and play seasons")
    build_cmd.add_argument("--seasons", type=int, default=3)
    measure_cmd = commands.add_parser("measure", help="time every read")
    measure_cmd.add_argument("--runs", type=int, default=7)
    measure_cmd.add_argument("--budget-ms", type=float)
    measure_cmd.add_argument("--max-queries", type=int)
    args = parser.parse_args()
    if args.command == "build":
        build(args.seasons)
    else:
        sys.exit(1 if measure(args.runs, args.budget_ms, args.max_queries) else 0)


if __name__ == "__main__":
    main()
