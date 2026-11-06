# Authentication + TLS

Adds login (salted SHA-256 password hashes) and an encrypted TLS connection to the file-sharing system.
Works with the team's existing `protocol.py` (`send_header` / `recv_header`). No changes to `protocol.py` needed.

## Files

| File | What it does |
|---|---|
| `password_store.py` | Stores users in `users.json` as salt + SHA-256 hash. `add_user()` and `check_login()`. |
| `add_user.py` | Command line tool to create a user (hidden password prompt). |
| `generate_tls_cert.py` | Creates `server.key` (private) and `server.crt` (public) with openssl. |
| `tls_helpers.py` | Builds the server and client TLS contexts (TLS 1.2 minimum). |
| `login_protocol.py` | The `AUTH` message exchange: `server_login()` and `client_login()`. Refuses non-TLS sockets. |
| `auth_demo_server.py` / `auth_demo_client.py` | Small standalone demo of login over TLS (progress check / video). |
| `test_password_store.py` | Unit tests for the password store. |
| `.gitignore` | Keeps `users.json`, keys and big test files out of git. |

## Quick start (local)

```
python generate_tls_cert.py            # once, creates server.key + server.crt
python add_user.py alice               # hidden password prompt, creates users.json
python -m unittest test_password_store -v

# terminal 1
python auth_demo_server.py
# terminal 2
python auth_demo_client.py --host 127.0.0.1 --user alice
```

On the GCP VM: run `generate_tls_cert.py` and `add_user.py` there, then copy `server.crt` to each client machine
(`scp` or `gcloud compute scp`), into the folder the client runs from. Every client needs the `server.crt` that
matches the `server.key` on the server it connects to.

## Wireshark comparison (progress check / video)

Capture with filter `tcp.port == 5050`, then right-click a packet > Follow > TCP Stream.

1. `python auth_demo_server.py --no-tls` and `python auth_demo_client.py --user alice --no-tls`:
   the JSON containing `"password": "..."` is readable in the stream.
2. Same without `--no-tls`: the stream is TLS records (handshake, then "Application Data"); nothing is readable.

## Hooking it into the real server and client

Server (`handle_client` in the teammate's server file):

```python
from login_protocol import server_login
from tls_helpers import make_server_context

tls_context = make_server_context()          # once, at server start-up

def handle_client(raw_conn, addr):
    conn = raw_conn
    try:
        conn = tls_context.wrap_socket(raw_conn, server_side=True)   # in the client's own thread
        username = server_login(conn, addr)
        if username is None:
            return                                                   # failed 3 times
        # ... your command loop (UPLOAD, DOWNLOAD, DIR, ...), `username` is the logged-in user
    except ConnectionError:
        pass                                                         # client went away
    finally:
        conn.close()
        raw_conn.close()
```

Client (`FileClient.__init__` or the connect command):

```python
from login_protocol import client_login
from tls_helpers import make_client_context

raw = socket.create_connection((host, port))
self.sock = make_client_context().wrap_socket(raw)
ok, message = client_login(self.sock, username, password)
if not ok:
    self.sock.close()
    raise PermissionError(message)
```

The existing `HELLO` command can be removed: `AUTH` replaces it. Reject every command except `AUTH` until
`server_login()` has returned a username (the code above already does this because the command loop only runs afterward).

## Security notes for the report

* Password is never stored (salt + SHA-256 hash only) and never sent in clear text (TLS).
* `compare_digest` for constant-time comparison; same error for unknown user and wrong password; 3 attempts per connection; audit line per attempt.
* Keys and the user database are gitignored and never hardcoded.
* Known simplifications (future work): plain SHA-256 instead of a slow hash (PBKDF2/bcrypt/argon2); self-signed
  certificate with hostname check disabled (certificate is still pinned through `load_verify_locations`);
  no account lockout across connections; no session tokens.
