import argparse
import json
import os
import subprocess
import threading
import time
from pathlib import Path


def _stream_to_file(stream, file_path: Path) -> None:
    with file_path.open("w", encoding="utf-8") as f:
        for line in stream:
            f.write(line)
            f.flush()


def _start_node(
    python_exec: str,
    host: str,
    port: int,
    bootstrap: str | None,
    fanout: int,
    ttl: int,
    peer_limit: int,
    ping_interval: float,
    peer_timeout: float,
    seed: int,
    pull_interval: float,
    ihave_max_ids: int,
    pow_k: int,
    log_path: Path,
) -> tuple[subprocess.Popen, threading.Thread]:
    args = [
        python_exec,
        "-m",
        "protocol.node",
        "--host",
        host,
        "--port",
        str(port),
        "--fanout",
        str(fanout),
        "--ttl",
        str(ttl),
        "--peer-limit",
        str(peer_limit),
        "--ping-interval",
        str(ping_interval),
        "--peer-timeout",
        str(peer_timeout),
        "--seed",
        str(seed),
        "--pull-interval",
        str(pull_interval),
        "--ihave-max-ids",
        str(ihave_max_ids),
        "--pow-k",
        str(pow_k),
    ]
    if bootstrap:
        args.extend(["--bootstrap", bootstrap])

    proc = subprocess.Popen(
        args,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    thread = threading.Thread(target=_stream_to_file, args=(proc.stdout, log_path), daemon=True)
    thread.start()
    return proc, thread


def _send_line(proc: subprocess.Popen, line: str) -> None:
    if proc.stdin is None:
        return
    try:
        proc.stdin.write(line + "\n")
        proc.stdin.flush()
    except BrokenPipeError:
        return


def _stop_process(proc: subprocess.Popen, timeout: float) -> None:
    if proc.poll() is not None:
        return
    _send_line(proc, "quit")
    start = time.time()
    while time.time() - start < timeout:
        if proc.poll() is not None:
            return
        time.sleep(0.1)
    proc.terminate()


def _parse_sizes(raw: str) -> list[int]:
    items = []
    for chunk in raw.split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        items.append(int(chunk))
    return items


def run_simulation(args: argparse.Namespace) -> None:
    out_root = Path(args.out_dir)
    out_root.mkdir(parents=True, exist_ok=True)
    run_tag = time.strftime("%Y%m%d_%H%M%S")
    root_dir = out_root / run_tag
    root_dir.mkdir(parents=True, exist_ok=True)

    modes: list[str]
    if args.mode == "both":
        modes = ["push", "hybrid"]
    else:
        modes = [args.mode]

    for mode in modes:
        pull_interval = args.pull_interval if mode == "hybrid" else 0.0
        for size in _parse_sizes(args.sizes):
            for run_index in range(args.runs):
                seed_base = args.seed_start + run_index
                run_dir = root_dir / f"mode_{mode}" / f"N{size}_seed{seed_base}"
                run_dir.mkdir(parents=True, exist_ok=True)

                base_port = args.base_port
                python_exec = args.python
                processes: list[subprocess.Popen] = []
                threads: list[threading.Thread] = []

                for i in range(size):
                    port = base_port + i
                    bootstrap = None if i == 0 else f"{args.host}:{base_port}"
                    log_path = run_dir / f"node_{i}.log"
                    proc, thread = _start_node(
                        python_exec=python_exec,
                        host=args.host,
                        port=port,
                        bootstrap=bootstrap,
                        fanout=args.fanout,
                        ttl=args.ttl,
                        peer_limit=args.peer_limit,
                        ping_interval=args.ping_interval,
                        peer_timeout=args.peer_timeout,
                        seed=seed_base + i,
                        pull_interval=pull_interval,
                        ihave_max_ids=args.ihave_max_ids,
                        pow_k=args.pow_k,
                        log_path=log_path,
                    )
                    processes.append(proc)
                    threads.append(thread)

                time.sleep(args.startup_wait)

                _send_line(processes[0], f"gossip {args.topic} {args.data}")
                time.sleep(args.gossip_wait)

                for proc in processes:
                    _stop_process(proc, args.shutdown_wait)

                for thread in threads:
                    thread.join(timeout=1.0)

                metadata = {
                    "mode": mode,
                    "size": size,
                    "seed_base": seed_base,
                    "fanout": args.fanout,
                    "ttl": args.ttl,
                    "peer_limit": args.peer_limit,
                    "ping_interval": args.ping_interval,
                    "peer_timeout": args.peer_timeout,
                    "pull_interval": pull_interval,
                    "ihave_max_ids": args.ihave_max_ids,
                    "pow_k": args.pow_k,
                    "base_port": base_port,
                    "host": args.host,
                    "topic": args.topic,
                    "data": args.data,
                    "startup_wait": args.startup_wait,
                    "gossip_wait": args.gossip_wait,
                    "timestamp": int(time.time() * 1000),
                }
                with (run_dir / "run.json").open("w", encoding="utf-8") as f:
                    json.dump(metadata, f, indent=2)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run gossip simulations and capture logs")
    parser.add_argument("--sizes", default="10,20,50")
    parser.add_argument("--runs", type=int, default=5)
    parser.add_argument("--mode", choices=["push", "hybrid", "both"], default="both")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--base-port", type=int, default=9000)
    parser.add_argument("--fanout", type=int, default=3)
    parser.add_argument("--ttl", type=int, default=8)
    parser.add_argument("--peer-limit", type=int, default=20)
    parser.add_argument("--ping-interval", type=float, default=5.0)
    parser.add_argument("--peer-timeout", type=float, default=15.0)
    parser.add_argument("--pull-interval", type=float, default=2.0)
    parser.add_argument("--ihave-max-ids", type=int, default=32)
    parser.add_argument("--pow-k", type=int, default=0)
    parser.add_argument("--seed-start", type=int, default=100)
    parser.add_argument("--startup-wait", type=float, default=2.0)
    parser.add_argument("--gossip-wait", type=float, default=8.0)
    parser.add_argument("--shutdown-wait", type=float, default=2.0)
    parser.add_argument("--topic", default="news")
    parser.add_argument("--data", default="hello")
    parser.add_argument("--out-dir", default=str(Path("scripts") / "out"))
    parser.add_argument("--python", default=os.environ.get("PYTHON", "python"))
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    run_simulation(args)


if __name__ == "__main__":
    main()
