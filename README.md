# Networks-Project# CNT3004 – Socket-Based Networked File Sharing Cloud Server

Team: <Carson>, <Talen>, <Matthew>  
Course section: <section>  
Last updated: 2026-11-05

## Overview
A multi-client file sharing server that runs on a Google Cloud VM. Clients connect over TCP sockets and can upload files, download files, list a directory and work with subfolders. The server logs every transfer to a CSV file, and an analysis module turns that log into statistics and graphs.

## Modules
| File | Purpose | Owner |
|------|---------|-------|
| `protocol.py` | Shared message format and send/receive helpers | <Name 1> |
| `client.py` | Command-line client | <Name 1> |
| `server.py` | TCP server, one thread per client, command handlers | <Name 3> (threading), <Name 2> (file operations) |
| `analysis.py` | Reads the transfer log, prints stats, makes graphs | <TBD> |

## Wire protocol (draft)
Every message is a 4-byte big-endian length followed by a UTF-8 JSON header. If the header has an integer `size` field, exactly that many raw bytes follow (file contents).

| Command | Header fields | Notes |
|---------|---------------|-------|
| `LIST` | – | Lists the current directory |
| `MKDIR` | `name` | Creates a subfolder |
| `CD` | `path` | Supports `..` and `a/b`; never leaves the storage root |
| `DELETE` | `name` | Deletes a file or empty folder |
| `UPLOAD` | `name`, `size` | `size` bytes follow the header |
| `DOWNLOAD` | `name` | Server replies with `size`, then the bytes |
| `QUIT` | – | Closes the session |

Every server reply has `status` (`ok` or `error`) and `msg`.

## Transfer log format
The server appends one CSV row per operation to `transfers.csv`:

`timestamp, client, operation, filename, bytes, duration_s, status`

The analysis module reads this file.

## Running (to be updated)
```
# server (on the GCP VM)
python3 server.py --port 5050

# client
python3 client.py --host <server-ip> --port 5050
```

## Progress
- [ ] Protocol agreed
- [ ] Client: connect + dir
- [ ] Client: upload / download
- [ ] Server: file operation functions
- [ ] Server: logging to CSV
- [ ] Server: multithreading
- [ ] Analysis: stats + graphs
- [ ] GCP deployment
- [ ] Report and video

## Rules for the team
- Commit often, with a message that says what you changed. The rubric grades the git log per member.
- Each person works mainly in their own module to avoid merge conflicts.
- Keep this README's protocol table in sync with the code.