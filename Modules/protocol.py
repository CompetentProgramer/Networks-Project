"""
Every message is:   [4-byte big-endian length][UTF-8 JSON header]
If the header contains an integer "size" field, exactly that many raw bytes
follow the header (used for file contents). This keeps commands human-readable
while still allowing efficient binary file transfer over a single TCP stream.

Commands (client -> server):
    LIST                      list the current directory
    MKDIR   {name}            create a subfolder
    CD      {path}            change directory ("..", "a/b", "/" allowed)
    DELETE  {name}            delete a file or empty folder
    UPLOAD  {name, size}      followed by <size> bytes
    DOWNLOAD{name}            server replies {status, size} then <size> bytes
    QUIT                      close the session

Replies (server -> client) always contain {"status": "ok"|"error", "msg": ...}.
"""

import json
import struct

DEFAULT_HOST = "0.0.0.0"
DEFAULT_PORT = 5050
CHUNK = 64 * 1024            # bytes per socket read/write while streaming files
MAX_HEADER = 1024 * 1024     # refuse absurd header sizes


def recv_exact(sock, n):
    """Read exactly n bytes from sock or raise ConnectionError."""
    buf = bytearray()
    while len(buf) < n:
        part = sock.recv(n - len(buf))
        if not part:
            raise ConnectionError("connection closed by peer")
        buf.extend(part)
    return bytes(buf)


def send_header(sock, header):
    data = json.dumps(header).encode("utf-8")
    sock.sendall(struct.pack(">I", len(data)) + data)


def recv_header(sock):
    (length,) = struct.unpack(">I", recv_exact(sock, 4))
    if length > MAX_HEADER:
        raise ValueError("header too large")
    return json.loads(recv_exact(sock, length).decode("utf-8"))


def send_file(sock, path, size):
    """Stream `size` bytes of the file at `path` to the socket."""
    sent = 0
    with open(path, "rb") as f:
        while sent < size:
            chunk = f.read(min(CHUNK, size - sent))
            if not chunk:
                raise IOError("file shrank while sending")
            sock.sendall(chunk)
            sent += len(chunk)
    return sent


def recv_file(sock, path, size):
    """Receive exactly `size` bytes from the socket and write them to `path`."""
    got = 0
    with open(path, "wb") as f:
        while got < size:
            chunk = sock.recv(min(CHUNK, size - got))
            if not chunk:
                raise ConnectionError("connection lost during transfer")
            f.write(chunk)
            got += len(chunk)
    return got