"""`mhs-vault`: serve the identity vault, or back it up and restore it (PRV-07).

Run inside the vault container, which has the vault's key file and database role:

    docker compose exec vault mhs-vault backup --out /backups/vault.mhsvb
    docker compose exec -T vault mhs-vault restore --in /backups/vault.mhsvb

The passphrase comes from MHS_BACKUP_PASSPHRASE(_FILE) or a prompt.
"""

import argparse
import getpass
import sys
from pathlib import Path

from mhs.stack import secret
from mhs.vault.backup import BackupError, make_backup, restore_backup


def passphrase(confirm: bool) -> str:
    given = secret("BACKUP_PASSPHRASE")
    if given:
        return given
    if not sys.stdin.isatty():
        sys.exit("Set MHS_BACKUP_PASSPHRASE or MHS_BACKUP_PASSPHRASE_FILE, or run with a terminal (-it).")
    first = getpass.getpass("Backup passphrase: ")
    if confirm and getpass.getpass("Again: ") != first:
        sys.exit("The passphrases don't match.")
    return first


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="mhs-vault", description="MHS identity vault")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("serve", help="run the vault service")
    b = sub.add_parser("backup", help="write an encrypted backup of the whole vault")
    b.add_argument("--out", type=Path, required=True)
    r = sub.add_parser("restore", help="restore a backup into an empty vault")
    r.add_argument("--in", dest="path", type=Path, required=True)
    args = parser.parse_args(argv)

    if args.command == "serve":
        from mhs.vault.service import serve

        serve()
        return

    from mhs.vault.service import store_from_env

    db, store = store_from_env()
    try:
        if args.command == "backup":
            blob = make_backup(db, passphrase(confirm=True))
            args.out.parent.mkdir(parents=True, exist_ok=True)
            args.out.write_bytes(blob)
            print(f"backup: {store.count()} entries, {len(store.households())} household(s) -> {args.out}")
        else:
            counts = restore_backup(db, args.path.read_bytes(), passphrase(confirm=False))
            print(f"restore: {counts['entries']} entries, {counts['households']} household(s)")
    except BackupError as e:
        sys.exit(f"{args.command} failed: {e}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
