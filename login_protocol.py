"""
login_protocol.py - The AUTH exchange between client and server.

Uses the team's protocol.py (send_header / recv_header: 4-byte length prefix
followed by a JSON header), so it fits into the same message format as every
other command.

Message flow (all inside the TLS connection):

    client -> server   {"cmd": "AUTH", "user": "alice", "password": "..."}
    server -> client   {"status": "ok",    "msg": "Welcome alice"}
                  or   {"status": "error", "msg": "Invalid credentials",
                        "attempts_left": 2}

After MAX_ATTEMPTS failures the server stops and the caller should close the
connection.

Safety guard: both functions refuse to run on a non-TLS socket unless you pass
allow_plaintext=True. That flag exists ONLY so the demo can show, in
Wireshark, what a password looks like without TLS.
"""

import ssl
import time
from typing import Optional, Tuple

from password_store import check_login
from protocol import recv_header, send_header

MAX_ATTEMPTS = 3


def _audit(addr, username, success):
    """One-line audit log: time, client address, username, result."""
    stamp = time.strftime("%Y-%m-%d %H:%M:%S")
    result = "SUCCESS" if success else "FAILED"
    where = f"{addr[0]}:{addr[1]}" if addr else "unknown"
    print(f"[AUTH {stamp}] {result} user={username!r} from {where}")


def _require_tls(sock, allow_plaintext):
    if not allow_plaintext and not isinstance(sock, ssl.SSLSocket):
        raise RuntimeError(
            "Refusing to send/receive credentials on a non-TLS socket. "
            "Wrap the socket with the context from tls_helpers.py first."
        )


def server_login(conn, addr=None, allow_plaintext=False) -> Optional[str]:
    """
    Run the login exchange on one client connection.

    Returns the authenticated username, or None if the client failed to log in.
    May raise ConnectionError if the client disconnects mid-login (let your
    handle_client's `except ConnectionError` deal with that).
    """
    _require_tls(conn, allow_plaintext)

    for attempt in range(1, MAX_ATTEMPTS + 1):
        header = recv_header(conn)

        if header.get("cmd") != "AUTH":
            send_header(conn, {"status": "error",
                               "msg": "Authenticate first: send AUTH",
                               "attempts_left": MAX_ATTEMPTS - attempt})
            continue

        username = str(header.get("user", ""))
        password = str(header.get("password", ""))

        if check_login(username, password):
            _audit(addr, username, True)
            send_header(conn, {"status": "ok", "msg": f"Welcome {username}"})
            return username

        _audit(addr, username, False)
        # Same message whether the user or the password was wrong, so an
        # attacker cannot find out which usernames exist.
        send_header(conn, {"status": "error",
                           "msg": "Invalid credentials",
                           "attempts_left": MAX_ATTEMPTS - attempt})

    return None


def client_login(sock, username, password, allow_plaintext=False) -> Tuple[bool, str]:
    """
    Send AUTH and wait for the answer. Returns (success, message_from_server).
    """
    _require_tls(sock, allow_plaintext)
    send_header(sock, {"cmd": "AUTH", "user": username, "password": password})
    reply = recv_header(sock)
    return reply.get("status") == "ok", reply.get("msg", "")
