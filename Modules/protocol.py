import json
import struct

def send_header(sock, dict):
    data = json.dumps(dict).encode("utf-8")
    length_prefix = struct.pack('!I', len(data))
    sock.sendall(length_prefix + data)

def recv_header(sock):
    data = recv_exact(sock, 4)
    length = struct.unpack('!I', data)[0]
    body = recv_exact(sock, length)
    return json.loads(body.decode("utf-8"))

def recv_exact(sock, n):
    buf = bytearray()
    while len(buf) < n:
        piece = sock.recv(n - len(buf))
        if piece == b'':
            raise ConnectionError("Peer closed connection")
        buf.extend(piece)
    return bytes(buf)