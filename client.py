"""
1. Interactive:
       python client.py --host <server-ip> --user alice
   then type: dir | mkdir <name> | cd <path> | upload <file> | download <name>
              | delete <name> | quit

2. As a library (used by analysis.py for the benchmark):
       c = FileClient(host, port, user, password)
       c.connect()
       c.upload("report.pdf")

Connection sequence:  TCP connect -> TLS handshake -> AUTH (login) -> commands.
Message format and helpers come from protocol.py; TLS and login come from
tls_helpers.py and login_protocol.py (authentication teammate's modules).

Assumed server replies (agree these with the server owner):
    LIST      -> {"status":"ok", "entries":[{"name":..., "type":"file"|"dir", "size":N}, ...]}
    MKDIR/CD/DELETE -> {"status":"ok", "msg":...}
    UPLOAD    -> client sends header {"cmd","name","size"} then <size> raw bytes,
                 server answers {"status":"ok", "msg":...} after receiving them
    DOWNLOAD  -> server answers {"status":"ok", "size":N} then <N> raw bytes
    any failure -> {"status":"error", "msg":"why"}
"""

import argparse
import getpass
import os
import socket
import ssl
import sys
import time

from login_protocol import client_login
from protocol import recv_file, recv_header, send_file, send_header
from tls_helpers import make_client_context

DEFAULT_PORT = 5050


class FileShareError(Exception):
    """Raised when the server answers with status "error"."""


class FileClient:
    """One connection to the server. Each public method is one user command."""

    def __init__(self, host, port, user, password, use_tls=True, cafile=None):
        self.host = host
        self.port = port
        self.user = user
        self.password = password
        self.use_tls = use_tls
        self.cafile = cafile            # path to server.crt (defaults to ./server.crt)
        self.sock = None

    # ---- connection ---------------------------------------------------------

    def connect(self):
        """TCP connect, TLS handshake, then log in. Raises on any failure."""
        raw = socket.create_connection((self.host, self.port), timeout=30)
        # Send small writes (header, then file bytes) immediately instead of waiting to batch them.
        # add a ~40 ms stall to every small transfer (found during analysis).
        raw.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        try:
            if self.use_tls:
                raw = make_client_context(self.cafile).wrap_socket(raw)
            ok, message = client_login(raw, self.user, self.password,
                                       allow_plaintext=not self.use_tls)
        except Exception:
            raw.close()
            raise
        if not ok:
            raw.close()
            raise PermissionError(message)
        self.sock = raw
        return message

    def close(self):
        """Tell the server we are leaving, then close the socket."""
        if self.sock is None:
            return
        try:
            send_header(self.sock, {"cmd": "QUIT"})
            recv_header(self.sock)
        except (OSError, ConnectionError):
            pass                         # server already gone; nothing to do
        finally:
            self.sock.close()
            self.sock = None

    # ---- helpers ------------------------------------------------------------

    def _request(self, header):
        """Send one command header and return the server's reply dict."""
        send_header(self.sock, header)
        return self._checked(recv_header(self.sock))

    @staticmethod
    def _checked(reply):
        """Turn an error reply into an exception so callers can't ignore it."""
        if reply.get("status") != "ok":
            raise FileShareError(reply.get("msg", "unknown server error"))
        return reply

    # ---- commands -----------------------------------------------------------

    def list_dir(self):
        """Return the list of entries in the server's current directory."""
        return self._request({"cmd": "LIST"}).get("entries", [])

    def mkdir(self, name):
        return self._request({"cmd": "MKDIR", "name": name}).get("msg", "")

    def cd(self, path):
        return self._request({"cmd": "CD", "path": path}).get("msg", "")

    def delete(self, name):
        return self._request({"cmd": "DELETE", "name": name}).get("msg", "")

    def upload(self, local_path, remote_name=None):
        """
        Upload a local file. Returns (bytes_sent, seconds).
        Timing covers sending the bytes AND waiting for the server's ok
        """
        size = os.path.getsize(local_path)
        name = remote_name or os.path.basename(local_path)
        start = time.perf_counter()
        send_header(self.sock, {"cmd": "UPLOAD", "name": name, "size": size})
        send_file(self.sock, local_path, size)
        self._checked(recv_header(self.sock))
        return size, time.perf_counter() - start

    def download(self, name, dest_dir="downloads"):
        """
        Download a file into dest_dir. Returns (bytes_received, seconds, saved_path).
        """
        os.makedirs(dest_dir, exist_ok=True)
        # basename() stops a malicious server from writing outside dest_dir
        dest = os.path.join(dest_dir, os.path.basename(name))
        start = time.perf_counter()
        send_header(self.sock, {"cmd": "DOWNLOAD", "name": name})
        reply = self._checked(recv_header(self.sock))
        size = int(reply["size"])
        recv_file(self.sock, dest, size)
        return size, time.perf_counter() - start, dest


# ---- interactive command loop -------------------------------------------------

def _print_entries(entries):
    """Print a directory listing; accepts dicts or plain strings."""
    if not entries:
        print("(empty)")
        return
    for e in entries:
        if isinstance(e, dict):
            kind = "<DIR> " if e.get("type") == "dir" else "      "
            size = "" if e.get("type") == "dir" else f"{e.get('size', 0):>12,} B"
            print(f"  {kind} {e.get('name', '?'):<30} {size}")
        else:
            print(f"  {e}")


def interactive(client):
    """Read commands from the keyboard until the user types quit."""
    print("Commands: dir | mkdir <name> | cd <path> | upload <file> | "
          "download <name> | delete <name> | quit")
    while True:
        try:
            line = input(f"{client.user}> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not line:
            continue
        cmd, _, arg = line.partition(" ")
        cmd, arg = cmd.lower(), arg.strip()
        try:
            if cmd in ("quit", "exit"):
                break
            elif cmd in ("dir", "ls", "list"):
                _print_entries(client.list_dir())
            elif cmd == "mkdir" and arg:
                print(client.mkdir(arg) or "Folder created")
            elif cmd == "cd" and arg:
                print(client.cd(arg) or f"Now in {arg}")
            elif cmd in ("delete", "rm") and arg:
                print(client.delete(arg) or "Deleted")
            elif cmd == "upload" and arg:
                size, secs = client.upload(arg)
                print(f"Uploaded {size:,} bytes in {secs:.3f}s "
                      f"({size * 8 / secs / 1e6:.2f} Mbit/s)")
            elif cmd == "download" and arg:
                size, secs, path = client.download(arg)
                print(f"Downloaded {size:,} bytes in {secs:.3f}s -> {path}")
            else:
                print("Unknown or incomplete command")
        except FileNotFoundError as err:
            print(f"Local file error: {err}")
        except FileShareError as err:
            print(f"Server error: {err}")
        # ConnectionError/OSError are not caught here: the session is dead,
        # main() reports it and exits.


def main():
    parser = argparse.ArgumentParser(description="CNT3004 file sharing client")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--user", required=True)
    parser.add_argument("--cafile", help="server.crt path (default ./server.crt)")
    parser.add_argument("--no-tls", action="store_true",
                        help="plaintext, ONLY for the Wireshark comparison")
    args = parser.parse_args()

    # The password comes from the environment (scripts) or a hidden prompt.
    password = os.environ.get("FILE_SHARE_PASSWORD") or \
        getpass.getpass(f"Password for {args.user}: ")

    client = FileClient(args.host, args.port, args.user, password,
                        use_tls=not args.no_tls, cafile=args.cafile)
    try:
        print(client.connect())
        interactive(client)
    except PermissionError as err:
        print(f"Login failed: {err}")
        sys.exit(1)
    except ssl.SSLError as err:
        print(f"TLS error: {err}")
        sys.exit(1)
    except (ConnectionError, OSError) as err:
        print(f"Connection problem: {err}")
        sys.exit(1)
    finally:
        client.close()


if __name__ == "__main__":
    main()