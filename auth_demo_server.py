"""
auth_demo_server.py - Small standalone server that demonstrates login + TLS.

Purpose: progress-check demo that works WITHOUT the full file server. It shows
the same pattern the real server's handle_client should use:

    one thread per client -> TLS handshake -> AUTH -> only then accept commands

Run (from the repo root, after generate_tls_cert.py and add_user.py):
    python auth_demo_server.py                # TLS on (default)
    python auth_demo_server.py --no-tls       # plaintext, ONLY for the Wireshark comparison

Commands accepted after a successful login:
    {"cmd": "WHOAMI"}  -> {"status": "ok", "msg": "<username>"}
    {"cmd": "QUIT"}    -> closes the connection
"""

import argparse
import socket
import ssl
import threading

from login_protocol import server_login
from protocol import recv_header, send_header
from tls_helpers import make_server_context


def handle_client(raw_conn, addr, tls_context):
    name = threading.current_thread().name
    conn = raw_conn
    try:
        # The TLS handshake happens in THIS client's thread so a slow or hostile
        # client cannot block the accept loop.
        if tls_context is not None:
            conn = tls_context.wrap_socket(raw_conn, server_side=True)

        username = server_login(conn, addr, allow_plaintext=(tls_context is None))
        if username is None:
            print(f"[*] {name}: {addr[0]}:{addr[1]} failed login, closing")
            return

        # Per-thread state: no lock needed because only this thread uses it.
        while True:
            header = recv_header(conn)
            cmd = header.get("cmd")
            if cmd == "WHOAMI":
                send_header(conn, {"status": "ok", "msg": username})
            elif cmd == "QUIT":
                send_header(conn, {"status": "ok", "msg": "Goodbye"})
                break
            else:
                send_header(conn, {"status": "error", "msg": f"Unknown command: {cmd}"})

    except ssl.SSLError as err:
        print(f"[*] {name}: TLS error from {addr[0]}:{addr[1]}: {err}")
    except ConnectionError:
        print(f"[*] {name}: {addr[0]}:{addr[1]} disconnected")
    finally:
        try:
            conn.close()
        except OSError:
            pass
        if conn is not raw_conn:
            try:
                raw_conn.close()
            except OSError:
                pass


def main():
    parser = argparse.ArgumentParser(description="Login + TLS demo server")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=5050)
    parser.add_argument("--no-tls", action="store_true",
                        help="plaintext mode, ONLY for the Wireshark comparison")
    args = parser.parse_args()

    tls_context = None if args.no_tls else make_server_context()
    mode = "PLAINTEXT (insecure demo)" if args.no_tls else "TLS"
    print(f"[*] Demo server on {args.host}:{args.port} using {mode}")

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind((args.host, args.port))
        server.listen(5)
        while True:
            raw_conn, addr = server.accept()
            threading.Thread(target=handle_client,
                             args=(raw_conn, addr, tls_context),
                             daemon=True).start()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n[*] Server stopped")
