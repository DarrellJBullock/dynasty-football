"""Account admin: `python -m app.accounts set-password EMAIL` sets a new password (asked
for, not typed on the command line) and signs the account out everywhere. Until password
reset emails arrive with deployment, this is how a forgotten password gets reset."""

import argparse
import getpass
import sys

from app.db import SessionLocal
from app.services.accounts import AuthError, set_password


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m app.accounts")
    commands = parser.add_subparsers(dest="command", required=True)
    reset = commands.add_parser("set-password", help="set an account's password")
    reset.add_argument("email")
    args = parser.parse_args()

    password = getpass.getpass("New password: ")
    if getpass.getpass("Again: ") != password:
        sys.exit("The passwords don't match.")
    with SessionLocal() as db:
        try:
            user = set_password(db, args.email, password)
        except AuthError as exc:
            sys.exit(exc.message)
        db.commit()
        print(f"Password set for {user.email}; signed out everywhere.")


if __name__ == "__main__":
    main()
