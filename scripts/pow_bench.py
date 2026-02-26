import argparse
import json
import time
from pathlib import Path
from statistics import mean, pstdev

from modules import security


def _parse_pow_ks(raw: str) -> list[int]:
    values = []
    for chunk in raw.split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        values.append(int(chunk))
    return values


def _benchmark(pow_k: int, runs: int) -> list[float]:
    samples = []
    node_id = f"bench-node-{pow_k}"
    for _ in range(runs):
        start = time.perf_counter()
        security.mine_pow(node_id, pow_k)
        end = time.perf_counter()
        samples.append((end - start) * 1000.0)
    return samples


def run_bench(args: argparse.Namespace) -> None:
    out_root = Path(args.out_dir)
    out_root.mkdir(parents=True, exist_ok=True)
    run_dir = out_root / time.strftime("%Y%m%d_%H%M%S")
    run_dir.mkdir(parents=True, exist_ok=True)

    rows = []
    for pow_k in _parse_pow_ks(args.pow_ks):
        samples = _benchmark(pow_k, args.runs)
        rows.append(
            {
                "pow_k": pow_k,
                "runs": args.runs,
                "mean_ms": mean(samples),
                "std_ms": pstdev(samples) if len(samples) > 1 else 0.0,
                "min_ms": min(samples),
                "max_ms": max(samples),
            }
        )

    rows.sort(key=lambda r: r["pow_k"])

    with (run_dir / "pow_times.json").open("w", encoding="utf-8") as f:
        json.dump(rows, f, indent=2)

    with (run_dir / "pow_times.csv").open("w", encoding="utf-8") as f:
        f.write("pow_k,runs,mean_ms,std_ms,min_ms,max_ms\n")
        for row in rows:
            f.write(
                f"{row['pow_k']},{row['runs']},{row['mean_ms']},{row['std_ms']},{row['min_ms']},{row['max_ms']}\n"
            )

    if args.plot:
        try:
            import matplotlib.pyplot as plt
        except Exception:
            return

        xs = [row["pow_k"] for row in rows]
        ys = [row["mean_ms"] for row in rows]
        es = [row["std_ms"] for row in rows]

        plt.figure()
        plt.errorbar(xs, ys, yerr=es, marker="o")
        plt.title("PoW Mining Time")
        plt.xlabel("pow_k")
        plt.ylabel("time_ms")
        plt.tight_layout()
        plt.savefig(run_dir / "pow_times.png")
        plt.close()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Benchmark PoW mining time")
    parser.add_argument("--pow-ks", default="2,3,4")
    parser.add_argument("--runs", type=int, default=5)
    parser.add_argument("--out-dir", default=str(Path("scripts") / "pow"))
    parser.add_argument("--plot", action="store_true")
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    run_bench(args)


if __name__ == "__main__":
    main()
