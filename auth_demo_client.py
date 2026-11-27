"""
auth_demo_client.py - Client for auth_demo_server.py (login + TLS demo).

Usage:
    python auth_demo_client.py --host 127.0.0.1 --user alice
    python auth_demo_client.py --host <GCP external IP> --user alice
    python auth_demo_client.py --host 127.0.0.1 --user alice --no-tls   # Wireshark comparison

Needs server.crt (copied from the server) in the current folder, unless TLS_CERT_FILE
points elsewhere. The password is asked with getpass, or read from the
FILE_SHARE_PASSWORD environment variable for scripted tests.
"""

import argparse
import getpass
import os
import socket
import ssl
import sys

from login_protocol import client_login
from protocol import recv_header, send_header #file from Carsons branch
from tls_helpers import make_client_context


def main():
    parser = argparse.ArgumentParser(description="Login + TLS demo client")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=5050)
    parser.add_argument("--user", required=True)
    parser.add_argument("--no-tls", action="store_true",
                        help="plaintext mode, ONLY for the Wireshark comparison")
    args = parser.parse_args()

    password = os.environ.get("FILE_SHARE_PASSWORD") or getpass.getpass(f"Password for {args.user}: ")

    sock = socket.create_connection((args.host, args.port))
    try:
        if not args.no_tls:
            sock = make_client_context().wrap_socket(sock)
            print(f"[*] TLS established ({sock.version()})")
        else:
            print("[!] PLAINTEXT mode - the password will be visible on the wire")

        ok, message = client_login(sock, args.user, password, allow_plaintext=args.no_tls)
        print(f"[*] Login {'OK' if ok else 'FAILED'}: {message}")
        if not ok:
            sys.exit(1)

        send_header(sock, {"cmd": "WHOAMI"})
        print("[*] WHOAMI ->", recv_header(sock))
        send_header(sock, {"cmd": "QUIT"})
        print("[*] QUIT   ->", recv_header(sock))

    except ssl.SSLError as err:
        print(f"[!] TLS error: {err}")
        sys.exit(1)
    except ConnectionError as err:
        print(f"[!] Connection problem: {err}")
        sys.exit(1)
    finally:
        sock.close()


if __name__ == "__main__":
    main()
