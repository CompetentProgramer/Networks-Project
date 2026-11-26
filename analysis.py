"""
  benchmark   Connects N clients at once, has each upload and download files of
              several sizes, and records every transfer to a CSV file.
  report      Reads that CSV (and optionally the server's own transfer log),
              prints summary tables, and saves graphs as PNG files.

HOW DATA IS STORED
  Plain CSV files, one row per transfer, appended with Python's csv module:
    benchmark.csv  (written by this module, measured at the CLIENT)
      run_id, timestamp, num_clients, client_id, operation,
      size_bytes, duration_s, throughput_mbps, status
    transfers.csv  (written by the server, measured at the SERVER; optional)
      timestamp, client, username, operation, filename, bytes, duration_s, status
  CSV was chosen because it opens in Excel, needs no database, and can be
  appended to safely by one writer at a time (the benchmark collects rows from
  its threads in memory and writes them once, so no file locking is needed).

  throughput_mbps = size_bytes * 8 / duration_s / 1,000,000  (megabits/second)

EXAMPLES
  export FILE_SHARE_PASSWORD=secret
  python analysis.py benchmark --host 127.0.0.1 --user alice \
        --sizes 1KB,100KB,1MB,10MB --clients 1,2,3 --repeats 3
  python analysis.py report --bench benchmark.csv --server-log transfers.csv
"""

import argparse
import csv
import os
import statistics
import sys
import tempfile
import threading
import time
from collections import defaultdict

from client import FileClient, FileShareError

BENCH_FIELDS = ["run_id", "timestamp", "num_clients", "client_id", "operation",
                "size_bytes", "duration_s", "throughput_mbps", "status"]


# =============================================================================
# Benchmark
# =============================================================================

def parse_size(text):
    """'10MB' -> 10_000_000, '512KB' -> 512_000, '2048' -> 2048."""
    text = text.strip().upper()
    for suffix, mult in (("GB", 10**9), ("MB", 10**6), ("KB", 10**3), ("B", 1)):
        if text.endswith(suffix):
            return int(float(text[:-len(suffix)]) * mult)
    return int(text)


def label_size(n):
    """Inverse of parse_size, for graph labels."""
    for suffix, mult in (("GB", 10**9), ("MB", 10**6), ("KB", 10**3)):
        if n >= mult:
            return f"{n / mult:g}{suffix}"
    return f"{n}B"


def make_test_file(directory, size):
    """Create a file of `size` random bytes (random so nothing compresses)."""
    path = os.path.join(directory, f"bench_{size}.bin")
    if not os.path.exists(path):
        with open(path, "wb") as f:
            remaining = size
            while remaining > 0:
                n = min(remaining, 1 << 20)
                f.write(os.urandom(n))
                remaining -= n
    return path


def client_worker(args, run_id, num_clients, client_id, files, start_barrier, rows, lock):
    """
    One simulated user: log in, then for each size upload + download + delete,
    `repeats` times. All workers of a run wait on the barrier so their transfers overlap
    """
    client = FileClient(args.host, args.port, args.user,
                        os.environ.get("FILE_SHARE_PASSWORD", ""),
                        use_tls=not args.no_tls, cafile=args.cafile)
    local = []                      # collect rows locally, merge under lock at the end

    def record(op, size, secs, status):
        mbps = size * 8 / secs / 1e6 if secs > 0 else 0.0
        local.append({"run_id": run_id, "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                      "num_clients": num_clients, "client_id": client_id,
                      "operation": op, "size_bytes": size,
                      "duration_s": round(secs, 6), "throughput_mbps": round(mbps, 3),
                      "status": status})

    try:
        client.connect()
    except Exception as err:        # still release the barrier so others don't hang
        print(f"[client {client_id}] login failed: {err}", file=sys.stderr)
        start_barrier.abort()
        return

    try:
        start_barrier.wait()
        for rep in range(args.repeats):
            for size, path in files:
                remote = f"bench_r{run_id}_c{client_id}_{rep}_{size}.bin"
                try:
                    sent, secs = client.upload(path, remote)
                    record("upload", sent, secs, "ok")
                    got, secs, saved = client.download(remote, dest_dir=args.download_dir)
                    record("download", got, secs, "ok")
                    os.remove(saved)
                    client.delete(remote)       # keep server storage tidy
                except (FileShareError, OSError) as err:
                    print(f"[client {client_id}] {size}B failed: {err}", file=sys.stderr)
                    record("upload", size, 0.0, "error")
    except threading.BrokenBarrierError:
        pass
    finally:
        client.close()
        with lock:
            rows.extend(local)


def run_benchmark(args):
    sizes = [parse_size(s) for s in args.sizes.split(",")]
    client_counts = [int(c) for c in args.clients.split(",")]
    os.makedirs(args.download_dir, exist_ok=True)
    rows, lock = [], threading.Lock()

    with tempfile.TemporaryDirectory() as tmp:
        files = [(s, make_test_file(tmp, s)) for s in sizes]
        for run_id, n in enumerate(client_counts, start=1):
            print(f"[run {run_id}] {n} simultaneous client(s), sizes "
                  f"{[label_size(s) for s in sizes]}, {args.repeats} repeat(s)")
            barrier = threading.Barrier(n)
            threads = [threading.Thread(target=client_worker,
                                        args=(args, run_id, n, cid, files, barrier, rows, lock))
                       for cid in range(1, n + 1)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()

    new_file = not os.path.exists(args.out)
    with open(args.out, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=BENCH_FIELDS)
        if new_file:
            writer.writeheader()
        writer.writerows(rows)
    ok = sum(1 for r in rows if r["status"] == "ok")
    print(f"Wrote {len(rows)} rows ({ok} ok) to {args.out}")


# =============================================================================
# Report
# =============================================================================

def load_csv(path):
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


def summarize_benchmark(rows):
    """Print mean/min/max throughput per (operation, size, num_clients)."""
    groups = defaultdict(list)
    for r in rows:
        if r["status"] == "ok":
            key = (r["operation"], int(r["size_bytes"]), int(r["num_clients"]))
            groups[key].append((float(r["throughput_mbps"]), float(r["duration_s"])))
    print(f"\n{'operation':<9} {'size':>7} {'clients':>7} {'n':>3} "
          f"{'mean Mbit/s':>12} {'min':>9} {'max':>9} {'mean time s':>12}")
    for (op, size, nc), vals in sorted(groups.items()):
        mb = [v[0] for v in vals]
        print(f"{op:<9} {label_size(size):>7} {nc:>7} {len(vals):>3} "
              f"{statistics.mean(mb):>12.2f} {min(mb):>9.2f} {max(mb):>9.2f} "
              f"{statistics.mean(v[1] for v in vals):>12.4f}")
    errors = sum(1 for r in rows if r["status"] != "ok")
    print(f"\nTotal transfers: {len(rows)}   errors: {errors}")
    return groups


def summarize_server_log(rows):
    """Per-operation and per-user totals from the server's own log."""
    by_op, by_user = defaultdict(lambda: [0, 0, 0.0]), defaultdict(lambda: [0, 0])
    for r in rows:
        if r.get("status") != "ok":
            continue
        op = by_op[r["operation"]]
        op[0] += 1
        op[1] += int(r["bytes"])
        op[2] += float(r["duration_s"])
        user = by_user[r.get("username", "?")]
        user[0] += 1
        user[1] += int(r["bytes"])
    print("\nServer log, by operation:")
    for op, (n, b, s) in sorted(by_op.items()):
        rate = b * 8 / s / 1e6 if s else 0
        print(f"  {op:<9} {n:>5} transfers {b:>14,} bytes  avg {rate:.2f} Mbit/s")
    print("Server log, by user:")
    for u, (n, b) in sorted(by_user.items()):
        print(f"  {u:<12} {n:>5} transfers {b:>14,} bytes")


def make_graphs(groups, outdir):
    """Save the figures used in the report. Needs matplotlib."""
    try:
        import matplotlib
        matplotlib.use("Agg")           # no display needed (works on a server)
        import matplotlib.pyplot as plt
    except ImportError:
        print("matplotlib not installed (pip install matplotlib); skipping graphs")
        return
    os.makedirs(outdir, exist_ok=True)
    sizes = sorted({k[1] for k in groups})
    counts = sorted({k[2] for k in groups})

    def mean_mbps(op, size, nc):
        v = groups.get((op, size, nc))
        return statistics.mean(x[0] for x in v) if v else None

    # Figure 1: throughput vs file size (single client baseline)
    base = counts[0]
    fig, ax = plt.subplots(figsize=(7, 4))
    for op in ("upload", "download"):
        ys = [mean_mbps(op, s, base) for s in sizes]
        ax.plot([label_size(s) for s in sizes], ys, marker="o", label=op)
    ax.set(xlabel="File size", ylabel="Throughput (Mbit/s)",
           title=f"Throughput vs file size ({base} client)")
    ax.legend(); ax.grid(alpha=0.3)
    fig.tight_layout(); fig.savefig(os.path.join(outdir, "fig1_throughput_vs_size.png"), dpi=150)
    plt.close(fig)

    # Figure 2: transfer time vs number of simultaneous clients, per size
    for op in ("upload", "download"):
        fig, ax = plt.subplots(figsize=(7, 4))
        for s in sizes:
            pts = [(nc, groups[(op, s, nc)]) for nc in counts if (op, s, nc) in groups]
            ax.plot([p[0] for p in pts],
                    [statistics.mean(x[1] for x in p[1]) for p in pts],
                    marker="o", label=label_size(s))
        ax.set(xlabel="Simultaneous clients", ylabel="Mean transfer time (s)",
               title=f"{op.capitalize()} time vs concurrent clients")
        ax.set_xticks(counts); ax.legend(title="File size"); ax.grid(alpha=0.3)
        fig.tight_layout(); fig.savefig(os.path.join(outdir, f"fig2_{op}_time_vs_clients.png"), dpi=150)
        plt.close(fig)

    # Figure 3: per-client throughput vs number of clients for the largest size
    big = sizes[-1]
    fig, ax = plt.subplots(figsize=(7, 4))
    width = 0.35
    for i, op in enumerate(("upload", "download")):
        ys = [mean_mbps(op, big, nc) or 0 for nc in counts]
        ax.bar([c + (i - 0.5) * width for c in range(len(counts))], ys, width, label=op)
    ax.set_xticks(range(len(counts))); ax.set_xticklabels(counts)
    ax.set(xlabel="Simultaneous clients", ylabel="Per-client throughput (Mbit/s)",
           title=f"Per-client throughput, {label_size(big)} file")
    ax.legend(); ax.grid(axis="y", alpha=0.3)
    fig.tight_layout(); fig.savefig(os.path.join(outdir, "fig3_per_client_throughput.png"), dpi=150)
    plt.close(fig)
    print(f"Saved graphs to {outdir}/")


def run_report(args):
    rows = load_csv(args.bench)
    if not rows:
        sys.exit("benchmark file is empty")
    groups = summarize_benchmark(rows)
    if args.server_log and os.path.exists(args.server_log):
        summarize_server_log(load_csv(args.server_log))
    make_graphs(groups, args.graphs)


# =============================================================================

def main():
    p = argparse.ArgumentParser(description="CNT3004 analysis module")
    sub = p.add_subparsers(dest="mode", required=True)

    b = sub.add_parser("benchmark", help="run concurrent transfers and record timings")
    b.add_argument("--host", default="127.0.0.1")
    b.add_argument("--port", type=int, default=5050)
    b.add_argument("--user", required=True)
    b.add_argument("--cafile")
    b.add_argument("--no-tls", action="store_true")
    b.add_argument("--sizes", default="1KB,100KB,1MB,10MB")
    b.add_argument("--clients", default="1,2,3", help="comma list of client counts, one run each")
    b.add_argument("--repeats", type=int, default=3)
    b.add_argument("--out", default="benchmark.csv")
    b.add_argument("--download-dir", default="bench_downloads")

    r = sub.add_parser("report", help="summarize CSV data and draw graphs")
    r.add_argument("--bench", default="benchmark.csv")
    r.add_argument("--server-log", default="transfers.csv")
    r.add_argument("--graphs", default="graphs")

    args = p.parse_args()
    run_benchmark(args) if args.mode == "benchmark" else run_report(args)


if __name__ == "__main__":
    main()