"""
password_store.py - Salted SHA-256 password storage for the file-sharing server.

What this file does
-------------------
* Stores users in a JSON file (users.json) as {"username": {"salt": hex, "hash": hex}}.
* The real password is NEVER written to disk. Only a random salt and
  sha256(salt + password) are stored.
* check_login() hashes the attempt with the stored salt and compares it in
  constant time.

Simplifications (mention these in the report's "future work"):
* Plain SHA-256 is fast, so a stolen users.json is easier to brute-force than
  with a slow hash such as PBKDF2/bcrypt/argon2.
* No account lockout and no session tokens.

users.json is listed in .gitignore - never commit it.
"""

import hashlib
import hmac
import json
import os

# Where the user database lives. Override with the USERS_FILE environment variable.
USERS_FILE = os.environ.get("USERS_FILE", "users.json")

SALT_BYTES = 16  # 128-bit random salt per user


def _hash_password(password, salt_hex):
    """Return sha256(salt + password) as a hex string."""
    salted = bytes.fromhex(salt_hex) + password.encode("utf-8")
    return hashlib.sha256(salted).hexdigest()


def load_users(path=None):
    """Read the user database. Returns {} if the file does not exist yet."""
    path = path or USERS_FILE
    if not os.path.exists(path):
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def add_user(username, password, path=None):
    """Create (or overwrite) a user with a fresh random salt."""
    path = path or USERS_FILE
    if not username or not password:
        raise ValueError("username and password must not be empty")

    users = load_users(path)
    salt_hex = os.urandom(SALT_BYTES).hex()
    users[username] = {
        "salt": salt_hex,
        "hash": _hash_password(password, salt_hex),
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(users, f, indent=2)
    try:
        os.chmod(path, 0o600)  # owner-only on Linux/macOS; ignored on Windows
    except OSError:
        pass


def check_login(username, password, path=None):
    """Return True only if the username exists and the password matches."""
    users = load_users(path or USERS_FILE)
    record = users.get(username)
    if record is None:
        # Do the same amount of hashing work so a missing user is not
        # noticeably faster than a wrong password.
        _hash_password(password, "00" * SALT_BYTES)
        return False

    attempt = _hash_password(password, record["salt"])
    # compare_digest takes the same time no matter where the strings differ.
    return hmac.compare_digest(attempt, record["hash"])
