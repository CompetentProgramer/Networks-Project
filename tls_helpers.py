"""
tls_helpers.py - Builds the TLS (ssl) contexts used by the server and the client.

Python's module is called "ssl" for historical reasons; it speaks TLS.
Minimum version is TLS 1.2.

Server side:  make_server_context()  -> ctx.wrap_socket(conn, server_side=True)
Client side:  make_client_context()  -> ctx.wrap_socket(sock)

Certificate files are created by generate_tls_cert.py:
    server.key  - PRIVATE key, stays on the server, never committed
    server.crt  - public certificate, copied to every client

Simplification (state this in the report): the client verifies that the
server presents exactly the certificate it trusts (server.crt) but does NOT
check the hostname, so connecting by raw IP address works without a
subjectAltName entry.
"""

import os
import ssl

CERT_FILE = os.environ.get("TLS_CERT_FILE", "server.crt")
KEY_FILE = os.environ.get("TLS_KEY_FILE", "server.key")


def make_server_context(certfile=None, keyfile=None):
    """Create the server-side TLS context. Call once at server start-up."""
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    ctx.load_cert_chain(certfile or CERT_FILE, keyfile or KEY_FILE)
    return ctx


def make_client_context(cafile=None):
    """Create the client-side TLS context that trusts only our server.crt."""
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)  # verify_mode defaults to CERT_REQUIRED
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    ctx.load_verify_locations(cafile or CERT_FILE)
    ctx.check_hostname = False  # see simplification note above
    return ctx
