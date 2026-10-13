"""Seed the database with the default fictional league.

Usage:
    python -m app.seed            # seed only if the database is empty
    python -m app.seed --reset    # wipe all game data and re-seed
"""

import argparse

from sqlalchemy import func, select

from app.config import get_settings
from app.db import SessionLocal
from app.models import League, Player, Team
from app.seed.generator import clear_database, generate_league
from app.services.accounts import ensure_user
from app.services.members import give_league


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reset", action="store_true", help="delete existing data first")
    parser.add_argument("--seed", type=int, default=get_settings().seed)
    args = parser.parse_args()

    with SessionLocal() as session:
        if args.reset:
            clear_database(session)
        elif session.scalar(select(func.count(League.id))):
            print("Database already has a league; use --reset to regenerate.")
            return
        league = generate_league(session, seed=args.seed)
        settings = get_settings()
        if settings.dev_user_email and settings.dev_user_password:
            owner = ensure_user(session, settings.dev_user_email, settings.dev_user_password)
            give_league(session, league, owner)
        session.commit()
        teams = session.scalar(select(func.count(Team.id)))
        players = session.scalar(select(func.count(Player.id)))
        print(f"Created {league.name}: {teams} teams, {players} players (seed {args.seed})"
              + (f", owned by {settings.dev_user_email}." if league.user_id else "."))


if __name__ == "__main__":
    main()
