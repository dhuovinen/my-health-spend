"""`mhs-admin`: create households and members, reset a member's MFA, import an ingest file. Run inside the app
container:

    docker compose exec app mhs-admin create-household "Example household"
    docker compose exec -it app mhs-admin add-member --household <id> --email a@example.com --name "A Member"
    docker compose exec app mhs-admin import --household <id> /srv/mhs/samples/example-ingest.json --yes
"""

import argparse
import getpass
import json
import sys
from pathlib import Path

from mhs.data import importer
from mhs.data.db import Database
from mhs.data.household_store import HouseholdStore
from mhs.data.keys import LocalKeyFile, db_keyring
from mhs.data.objects import LocalObjectStore
from mhs.stack import load_app_config
from mhs.web.household.files import EncryptedFiles
from mhs.web.household.auth import AccountError, Accounts


def accounts_from_env() -> tuple[Database, Accounts]:
    config = load_app_config()
    db = Database(config.database_url, max_size=2)
    return db, Accounts(db, db_keyring(db, LocalKeyFile(config.key_file), "app.household_keys"))


def import_file(accounts: Accounts, household_id: str, path: Path, commit: bool, replace_edits: bool) -> None:
    """Preview an ingest file for a household and, with commit, save it (the Release 0 migration path)."""
    if accounts.household_name(household_id) is None:
        raise AccountError("No such household.")
    try:
        data = json.loads(path.read_text())
    except (OSError, ValueError) as e:
        raise AccountError(f"Can't read {path}: {e}") from None
    store = HouseholdStore(accounts.db, household_id)
    plan = importer.prepare(data, store, path.name, path.parent)
    for e in plan.errors:
        print(f"error: {e}")
    if not plan.ok:
        raise AccountError("Nothing was saved: fix the errors and import again.")
    for w in plan.warnings:
        print(f"warning: {w}")
    for section, c in plan.counts.items():
        print(f"{section}: {c['new']} new, {c['updated']} updated, {c['unchanged']} unchanged")
    for k in plan.kept:
        what = "deleted in the app" if not k.fields else "changed in the app: " + ", ".join(k.fields)
        print(f"member edit {'replaced' if replace_edits else 'kept'}: {k.section} {k.id} ({what})")
    if not commit:
        print("Preview only: run again with --yes to save.")
        return
    config = load_app_config()
    files = EncryptedFiles(LocalObjectStore(config.objects_dir), accounts.keyring, household_id)
    summary = importer.commit(plan, store, files, replace_edits=replace_edits)
    print(f"saved: {json.dumps(summary)}")


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
    i = sub.add_parser("import", help="import an ingest file (and the files beside it) into a household")
    i.add_argument("--household", required=True)
    i.add_argument("path", type=Path)
    i.add_argument("--yes", action="store_true", help="save; without it, only preview")
    i.add_argument("--replace-edits", action="store_true", help="let the file overwrite edits made in the app")
    a = sub.add_parser("ai-extraction", help="let Claude read this household's scrubbed documents (ADR-028, ADR-034)")
    a.add_argument("--household", required=True)
    a.add_argument("state", choices=["on", "off", "status"])
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
        elif args.command == "import":
            import_file(accounts, args.household, args.path, args.yes, args.replace_edits)
        elif args.command == "ai-extraction":
            if args.state != "status":
                accounts.set_ai_extraction(args.household, args.state == "on")
            state = "on" if accounts.ai_extraction(args.household) else "off"
            print(f"AI extraction is {state} for household {args.household}. It needs a worker with "
                  "MHS_EXTRACTOR=claude; without one, documents are read with the layout rules after a minute.")
    except AccountError as e:
        sys.exit(str(e))
    finally:
        db.close()


if __name__ == "__main__":
    main()
