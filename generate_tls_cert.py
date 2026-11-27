"""
generate_tls_cert.py - Create a self-signed TLS certificate and private key.

Usage (run ONCE on the machine that runs the server, e.g. the GCP VM):
    python generate_tls_cert.py          # refuses to overwrite existing files
    python generate_tls_cert.py --force  # overwrite

Produces:
    server.key  PRIVATE key - stays on the server, never commit it
    server.crt  public certificate - copy it to every client machine
                (for the GCP server: scp it down from the VM)

Needs the `openssl` command line tool (Linux/macOS: preinstalled; Windows: it
ships with Git for Windows).
"""

import os
import subprocess
import sys

KEY_FILE = "server.key"
CERT_FILE = "server.crt"


def main():
    force = "--force" in sys.argv

    if not force and (os.path.exists(KEY_FILE) or os.path.exists(CERT_FILE)):
        print(f"{KEY_FILE} or {CERT_FILE} already exists. Use --force to overwrite.")
        print("Remember: clients must have the server.crt that matches the server's server.key.")
        sys.exit(1)

    command = [
        "openssl", "req", "-x509",
        "-newkey", "rsa:2048", "-nodes",
        "-keyout", KEY_FILE,
        "-out", CERT_FILE,
        "-days", "365",
        "-subj", "/CN=cnt3004-file-server",
    ]

    try:
        subprocess.run(command, check=True)
    except FileNotFoundError:
        print("openssl was not found. Install it (or use Git Bash, which includes it) and retry.")
        sys.exit(1)
    except subprocess.CalledProcessError as err:
        print(f"openssl failed: {err}")
        sys.exit(1)

    try:
        os.chmod(KEY_FILE, 0o600)  # owner-only on Linux/macOS; ignored on Windows
    except OSError:
        pass

    print(f"Created {KEY_FILE} (keep secret) and {CERT_FILE} (give to clients).")


if __name__ == "__main__":
    main()
