#!/usr/bin/env python3
"""Create local secrets without exposing passwords in shell history or logs."""
from __future__ import annotations

import argparse
import getpass
import os
from pathlib import Path
import secrets
import shutil

from argon2 import PasswordHasher
from dotenv import dotenv_values, set_key


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--path", type=Path, default=Path(".env"))
    parser.add_argument("--generate", action="store_true", help="Generate a private local bootstrap password")
    args = parser.parse_args()
    if not args.path.exists():
        shutil.copyfile(Path(__file__).resolve().parents[1] / ".env.example", args.path)
    os.chmod(args.path, 0o600)
    values = dotenv_values(args.path)
    if not values.get("PT_ADMIN_PASSWORD_HASH"):
        password = secrets.token_urlsafe(24) if args.generate else getpass.getpass("Dashboard password (14+ characters): ")
        if len(password) < 14:
            raise SystemExit("Use at least 14 characters.")
        if not args.generate and password != getpass.getpass("Confirm password: "):
            raise SystemExit("Passwords do not match.")
        if args.generate:
            state_dir = Path(values.get("PT_STATE_DIR") or "var")
            state_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
            credential_path = state_dir / "initial-admin-password.txt"
            descriptor = os.open(credential_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(descriptor, "w") as handle:
                handle.write(password + "\n")
            print(f"Initial admin password stored privately in {credential_path}; remove after saving it securely.")
        set_key(args.path, "PT_ADMIN_PASSWORD_HASH", PasswordHasher().hash(password))
    if len(values.get("PT_API_TOKEN") or "") < 32:
        set_key(args.path, "PT_API_TOKEN", secrets.token_urlsafe(48))
    print(f"Configured {args.path}; keep it private and never commit it.")


if __name__ == "__main__":
    main()
