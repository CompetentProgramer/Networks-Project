"""
add_user.py - Create or update a login for the file-sharing server.

Usage (run on the machine that runs the server):
    python add_user.py alice

The password is typed at a hidden prompt (getpass), so it never appears on
screen, in shell history, or in the repository.
"""

import getpass
import sys

from password_store import USERS_FILE, add_user


def main():
    if len(sys.argv) != 2:
        print("Usage: python add_user.py <username>")
        sys.exit(1)

    username = sys.argv[1]
    password = getpass.getpass(f"Password for {username}: ")
    confirm = getpass.getpass("Repeat password: ")

    if password != confirm:
        print("Passwords do not match. Nothing saved.")
        sys.exit(1)
    if not password:
        print("Empty password not allowed. Nothing saved.")
        sys.exit(1)

    add_user(username, password)
    print(f"Saved user {username!r} in {USERS_FILE} (salt + SHA-256 hash only).")


if __name__ == "__main__":
    main()
