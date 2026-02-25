import argparse
import json
import math
import re
from pathlib import Path
from statistics import mean, pstdev


RECV_RE = re.compile(
    r"^\[(?P<ts>\d+)\].*RECV msg_type=GOSSIP msg_id=(?P<msg_id>\S+) first_seen=true node_id=(?P<node_id>\S+) recv_ms=(?P<recv_ms>\d+)"
)
SEND_RE = re.compile(r"^\[(?P<ts>\d+)\].*SEND msg_type=(?P<msg_type>\S+) msg_id=(?P<msg_id>\S+)")
GOSSIP_ID_RE = re.compile(r"GOSSIP msg_id=(?P<msg_id>\S+)")


def _load_runs(root: Path) -> list[Path]:
    return list(root.rglob("run.json"))


def _parse_log(path: Path) -> dict[str, list[dict]]:
    recv_events: list[dict] = []
    send_events: list[dict] = []
    gossip_ids: list[str] = []

    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            match = RECV_RE.match(line)
            if match:
                recv_events.append(
                    {
                        "ts": int(match.group("ts")),
                        "msg_id": match.group("msg_id"),
                        "node_id": match.group("node_id"),
                        "recv_ms": int(match.group("recv_ms")),
                    }
                )
                continue
            match = SEND_RE.match(line)
            if match:
                send_events.append(
                    {
                        "ts": int(match.group("ts")),
                        "msg_id": match.group("msg_id"),
                        "msg_type": match.group("msg_type"),
                    }
                )
                continue
            match = GOSSIP_ID_RE.search(line)
            if match:
                gossip_ids.append(match.group("msg_id"))

    return {"recv": recv_events, "send": send_events, "gossip_ids": gossip_ids}


def _pick_target_msg_id(events: list[dict], gossip_ids: list[str]) -> str | None:
    if gossip_ids:
        return gossip_ids[0]
    if not events:
        return None
    counts: dict[str, int] = {}
    for item in events:
        msg_id = item["msg_id"]
        counts[msg_id] = counts.get(msg_id, 0) + 1
    return max(counts.items(), key=lambda x: x[1])[0]


def _analyze_run(run_dir: Path, size: int) -> dict:
    recv_events: list[dict] = []
    send_events: list[dict] = []
    gossip_ids: list[str] = []

    for log_path in sorted(run_dir.glob("node_*.log")):
        parsed = _parse_log(log_path)
        recv_events.extend(parsed["recv"])
        send_events.extend(parsed["send"])
        gossip_ids.extend(parsed["gossip_ids"])

    target_id = _pick_target_msg_id(recv_events, gossip_ids)
    if not target_id:
        return {
            "complete": False,
            "reason": "no_gossip_id",
            "coverage": 0.0,
            "convergence_ms": None,
            "overhead": None,
            "msg_id": None,
        }

    first_seen_by_node: dict[str, int] = {}
    for item in recv_events:
        if item["msg_id"] != target_id:
            continue
        node_id = item["node_id"]
        if node_id not in first_seen_by_node or item["recv_ms"] < first_seen_by_node[node_id]:
            first_seen_by_node[node_id] = item["recv_ms"]

    seen_times = sorted(first_seen_by_node.values())
    coverage = len(seen_times) / max(1, size)
    target_count = math.ceil(0.95 * size)

    if len(seen_times) < target_count:
        return {
            "complete": False,
            "reason": "insufficient_coverage",
            "coverage": coverage,
            "convergence_ms": None,
            "overhead": None,
            "msg_id": target_id,
        }

    t0 = seen_times[0]
    t95 = seen_times[target_count - 1]
    convergence_ms = t95 - t0

    overhead = 0
    for item in send_events:
        if t0 <= item["ts"] <= t95:
            overhead += 1

    return {
        "complete": True,
        "reason": None,
        "coverage": coverage,
        "convergence_ms": convergence_ms,
        "overhead": overhead,
        "msg_id": target_id,
    }


def _group_stats(rows: list[dict]) -> dict:
    modes = sorted({row["mode"] for row in rows})
    sizes = sorted({row["size"] for row in rows})
    summary: list[dict] = []

    for mode in modes:
        for size in sizes:
            subset = [row for row in rows if row["mode"] == mode and row["size"] == size and row["complete"]]
            if not subset:
                summary.append(
                    {
                        "mode": mode,
                        "size": size,
                        "runs": 0,
                        "convergence_mean": None,
                        "convergence_std": None,
                        "overhead_mean": None,
                        "overhead_std": None,
                        "coverage_mean": None,
                    }
                )
                continue

            conv = [row["convergence_ms"] for row in subset if row["convergence_ms"] is not None]
            over = [row["overhead"] for row in subset if row["overhead"] is not None]
            cov = [row["coverage"] for row in subset]

            summary.append(
                {
                    "mode": mode,
                    "size": size,
                    "runs": len(subset),
                    "convergence_mean": mean(conv) if conv else None,
                    "convergence_std": pstdev(conv) if len(conv) > 1 else 0.0,
                    "overhead_mean": mean(over) if over else None,
                    "overhead_std": pstdev(over) if len(over) > 1 else 0.0,
                    "coverage_mean": mean(cov) if cov else None,
                }
            )

    return {"summary": summary, "modes": modes, "sizes": sizes}


def _write_csv(path: Path, rows: list[dict], fieldnames: list[str]) -> None:
    header = ",".join(fieldnames)
    with path.open("w", encoding="utf-8") as f:
        f.write(header + "\n")
        for row in rows:
            values = []
            for name in fieldnames:
                value = row.get(name)
                values.append("" if value is None else str(value))
            f.write(",".join(values) + "\n")


def _plot(summary_rows: list[dict], out_dir: Path) -> None:
    try:
        import matplotlib.pyplot as plt
    except Exception:
        return

    modes = sorted({row["mode"] for row in summary_rows})
    sizes = sorted({row["size"] for row in summary_rows})

    def plot_metric(metric_key: str, std_key: str, title: str, filename: str) -> None:
        plt.figure()
        for mode in modes:
            xs = []
            ys = []
            es = []
            for size in sizes:
                row = next((r for r in summary_rows if r["mode"] == mode and r["size"] == size), None)
                if row is None or row[metric_key] is None:
                    continue
                xs.append(size)
                ys.append(row[metric_key])
                es.append(row[std_key] if row[std_key] is not None else 0.0)
            if xs:
                plt.errorbar(xs, ys, yerr=es, marker="o", label=mode)
        plt.title(title)
        plt.xlabel("N")
        plt.ylabel(metric_key)
        plt.legend()
        plt.tight_layout()
        plt.savefig(out_dir / filename)
        plt.close()

    plot_metric("convergence_mean", "convergence_std", "Convergence Time", "convergence.png")
    plot_metric("overhead_mean", "overhead_std", "Message Overhead", "overhead.png")


def run_analysis(args: argparse.Namespace) -> None:
    in_root = Path(args.input)
    out_dir = Path(args.output)
    out_dir.mkdir(parents=True, exist_ok=True)

    run_files = _load_runs(in_root)
    rows: list[dict] = []

    for run_file in run_files:
        with run_file.open("r", encoding="utf-8") as f:
            meta = json.load(f)
        run_dir = run_file.parent
        size = int(meta["size"])
        result = _analyze_run(run_dir, size)
        row = {**meta, **result, "run_dir": str(run_dir)}
        rows.append(row)

    rows.sort(key=lambda r: (r.get("mode"), r.get("size"), r.get("seed_base")))

    _write_csv(out_dir / "runs.csv", rows, sorted(rows[0].keys()) if rows else [])
    summary_info = _group_stats(rows)
    _write_csv(out_dir / "summary.csv", summary_info["summary"], list(summary_info["summary"][0].keys()) if summary_info["summary"] else [])

    with (out_dir / "summary.json").open("w", encoding="utf-8") as f:
        json.dump(summary_info, f, indent=2)

    if args.plot:
        _plot(summary_info["summary"], out_dir)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Analyze gossip simulation logs")
    parser.add_argument("--input", default=str(Path("scripts") / "out"))
    parser.add_argument("--output", default=str(Path("scripts") / "results"))
    parser.add_argument("--plot", action="store_true")
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    run_analysis(args)


if __name__ == "__main__":
    main()
