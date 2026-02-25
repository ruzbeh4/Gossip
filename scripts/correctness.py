import argparse
import json
import socket
import time
from pathlib import Path

from scripts.analyze import _analyze_run
from scripts.simulate import _start_node, _stop_process, _send_line


def _udp_port_available(host: str, port: int) -> bool:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.bind((host, port))
        return True
    except OSError:
        return False
    finally:
        sock.close()


def _find_free_base_port(host: str, size: int, start_port: int = 9100, max_port: int = 65000) -> int:
    width = max(1, size)
    for base_port in range(start_port, max_port - width):
        if all(_udp_port_available(host, base_port + offset) for offset in range(width)):
            return base_port
    raise RuntimeError("No free UDP port block found for requested network size")


def run_check(args: argparse.Namespace) -> int:
    run_dir = Path(args.out_dir) / time.strftime("%Y%m%d_%H%M%S")
    run_dir.mkdir(parents=True, exist_ok=True)

    base_port = args.base_port
    if base_port <= 0:
        base_port = _find_free_base_port(args.host, args.size)

    processes = []
    threads = []
    for i in range(args.size):
        port = base_port + i
        bootstrap = None if i == 0 else f"{args.host}:{base_port}"
        log_path = run_dir / f"node_{i}.log"
        proc, thread = _start_node(
            python_exec=args.python,
            host=args.host,
            port=port,
            bootstrap=bootstrap,
            fanout=args.fanout,
            ttl=args.ttl,
            peer_limit=args.peer_limit,
            ping_interval=args.ping_interval,
            peer_timeout=args.peer_timeout,
            seed=args.seed_start + i,
            pull_interval=0.0,
            ihave_max_ids=args.ihave_max_ids,
            pow_k=args.pow_k,
            log_path=log_path,
        )
        processes.append(proc)
        threads.append(thread)

    startup_wait = args.startup_wait
    if startup_wait <= 0:
        startup_wait = max(2.0, min(12.0, args.size * 0.12))

    gossip_wait = args.gossip_wait
    if gossip_wait <= 0:
        gossip_wait = max(8.0, min(30.0, args.ttl * 1.5))

    time.sleep(startup_wait)
    _send_line(processes[0], f"gossip {args.topic} {args.data}")
    time.sleep(gossip_wait)

    for proc in processes:
        _stop_process(proc, args.shutdown_wait)

    for thread in threads:
        thread.join(timeout=1.0)

    metadata = {
        "mode": "push",
        "size": args.size,
        "seed_base": args.seed_start,
    }
    with (run_dir / "run.json").open("w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2)

    result = _analyze_run(run_dir, args.size)
    coverage = result.get("coverage", 0.0)

    print(f"coverage={coverage:.2f}")
    return 0 if coverage >= args.min_coverage else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Basic correctness check")
    parser.add_argument("--size", type=int, default=10)
    parser.add_argument("--min-coverage", type=float, default=0.9)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--base-port", type=int, default=0, help="UDP base port; <=0 auto-selects a free range")
    parser.add_argument("--fanout", type=int, default=3)
    parser.add_argument("--ttl", type=int, default=8)
    parser.add_argument("--peer-limit", type=int, default=20)
    parser.add_argument("--ping-interval", type=float, default=5.0)
    parser.add_argument("--peer-timeout", type=float, default=15.0)
    parser.add_argument("--ihave-max-ids", type=int, default=32)
    parser.add_argument("--pow-k", type=int, default=0)
    parser.add_argument("--seed-start", type=int, default=200)
    parser.add_argument("--startup-wait", type=float, default=0.0, help="seconds; <=0 enables adaptive default")
    parser.add_argument("--gossip-wait", type=float, default=0.0, help="seconds; <=0 enables adaptive default")
    parser.add_argument("--shutdown-wait", type=float, default=2.0)
    parser.add_argument("--topic", default="news")
    parser.add_argument("--data", default="hello")
    parser.add_argument("--out-dir", default=str(Path("scripts") / "correctness"))
    parser.add_argument("--python", default="python")
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    raise SystemExit(run_check(args))


if __name__ == "__main__":
    main()
