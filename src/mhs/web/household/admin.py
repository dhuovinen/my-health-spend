"""`mhs-admin`: create households and members, reset a member's MFA. Run inside the app container:

    docker compose exec app mhs-admin create-household "Example household"
    docker compose exec -it app mhs-admin add-member --household <id> --email a@example.com --name "A Member"
"""

import argparse
import getpass
import sys

from mhs.data.db import Database
from mhs.data.keys import LocalKeyFile, db_keyring
from mhs.stack import load_app_config
from mhs.web.household.auth import AccountError, Accounts


def accounts_from_env() -> tuple[Database, Accounts]:
    config = load_app_config()
    db = Database(config.database_url, max_size=2)
    return db, Accounts(db, db_keyring(db, LocalKeyFile(config.key_file), "app.household_keys"))


def read_password(from_stdin: bool) -> str:
    if from_stdin:
        return sys.stdin.readline().rstrip("\n")
    first = getpass.getpass("Password (12+ characters): ")
    if getpass.getpass("Again: ") != first:
        sys.exit("The passwords don't match.")
    return first


def show_totp(accounts: Accounts, email: str, totp_secret: str) -> None:
    print("Add this to an authenticator app (shown once):")
    print(f"  secret: {totp_secret}")
    print(f"  uri:    {accounts.provisioning_uri(email, totp_secret)}")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="mhs-admin", description="Manage households and members")
    sub = parser.add_subparsers(dest="command", required=True)
    h = sub.add_parser("create-household")
    h.add_argument("name")
    m = sub.add_parser("add-member")
    m.add_argument("--household", required=True)
    m.add_argument("--email", required=True)
    m.add_argument("--name", required=True)
    m.add_argument("--password-stdin", action="store_true", help="read the password from the first line of stdin")
    r = sub.add_parser("reset-mfa", help="issue a new authenticator secret and end the member's sessions")
    r.add_argument("--email", required=True)
    args = parser.parse_args(argv)

    db, accounts = accounts_from_env()
    try:
        if args.command == "create-household":
            print(accounts.create_household(args.name))
        elif args.command == "add-member":
            member, totp_secret = accounts.add_member(args.household, args.email, args.name,
                                                      read_password(args.password_stdin))
            print(f"member {member.id} added to household {member.household_id}")
            show_totp(accounts, member.email, totp_secret)
        elif args.command == "reset-mfa":
            show_totp(accounts, args.email, accounts.reset_mfa(args.email))
    except AccountError as e:
        sys.exit(str(e))
    finally:
        db.close()


if __name__ == "__main__":
    main()
