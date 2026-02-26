# Gossip Protocol (Async UDP)

Design, implementation, and local test harness for a Peer-to-Peer Gossip protocol using Python `asyncio` and UDP.

This repository currently includes:

- Core protocol package: `protocol/`
- Mandatory extensions package: `modules/`
- Unit tests for core logic and extensions
- Simulation, analysis, and correctness scripts

## Features Implemented

- UDP-based JSON message transport (`asyncio.DatagramProtocol`)
- Bootstrap flow: `HELLO -> GET_PEERS -> PEERS_LIST`
- Peer management with periodic `PING/PONG` and timeout removal
- Push gossip with:
  - `msg_id` seen-set duplicate suppression
  - TTL decrement + bounded random fanout forwarding
- Hybrid push-pull extension:
  - `IHAVE` / `IWANT`
  - periodic pull loop with `pull_interval`
- Sybil-resistance extension:
  - PoW mining (`sha256(node_id || nonce)`) with difficulty `pow_k`
  - HELLO rejection when PoW is invalid
- Robust parsing behavior: invalid JSON datagrams are dropped safely

## Folder Structure

```text
gossip_project/
├── protocol/
│   ├── __init__.py
│   ├── node.py
│   ├── network.py
│   ├── messages.py
│   ├── peers.py
│   └── gossip.py
├── modules/
│   ├── __init__.py
│   ├── hybrid.py
│   └── security.py
├── tests/
│   ├── test_messages.py
│   ├── test_security.py
│   └── test_gossip_logic.py
├── scripts/
│   ├── simulate.py
│   ├── analyze.py
│   ├── pow_bench.py
│   └── correctness.py
├── requirements.txt
└── README.md
```

## Requirements

- Python 3.11+ (3.10 also works in most cases)
- OS: Windows / Linux / macOS

## Setup (with Virtual Environment)

### Windows (PowerShell)

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

### Linux/macOS (bash/zsh)

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```

## Run a Node

Run via module entrypoint:

```bash
python -m protocol.node --port 9000 --fanout 3 --ttl 8 --peer-limit 20 --ping-interval 5 --peer-timeout 15 --seed 42
```

Or use the root executable wrapper (for all flags):

```bash
./node --port 8000 --bootstrap 127.0.0.1:9000 --fanout 3 --ttl 8 --peer-limit 20 --ping-interval 5 --peer-timeout 15 --seed 42
```

Windows `cmd`/PowerShell wrapper:

```powershell
.\node.bat --port 8000 --bootstrap 127.0.0.1:9000 --fanout 3 --ttl 8 --peer-limit 20 --ping-interval 5 --peer-timeout 15 --seed 42
```

Run another node and connect to bootstrap:

```bash
python -m protocol.node --port 9001 --bootstrap 127.0.0.1:9000 --fanout 3 --ttl 8 --peer-limit 20 --ping-interval 5 --peer-timeout 15 --seed 7
```

### Enable Hybrid Push-Pull

```bash
python -m protocol.node --port 9002 --bootstrap 127.0.0.1:9000 --pull-interval 3 --ihave-max-ids 32
```

### Enable PoW Gatekeeping

```bash
python -m protocol.node --port 9003 --bootstrap 127.0.0.1:9000 --pow-k 4
```

## Node CLI Commands (stdin)

When a node is running, type one of:

- `gossip <topic> <text>` publish gossip
- `peers` show known peers
- `stats` show counters
- `messages [limit]` show message observations (`first_seen=true/false`)
- `mode logs` switch to realtime logs mode
- `mode command` switch to quiet command mode (logs buffered)
- `/` toggle between logs/command modes
- `help` show help
- `quit` stop node

Plain text input is ignored; use `gossip <topic> <text>` to publish.

### Terminal UX Modes (minimal, no extra libraries)

- `logs` mode:
  - Background events print immediately.
  - Best for observing protocol behavior.

- `command` mode:
  - Background logs are buffered (not printed while typing).
  - Use this when you want clean command entry.
  - Prompt changes to `cmd> `.

- Mode switch behavior:
  - Enter `/` to toggle modes quickly.
  - When switching from `command` to `logs`, buffered logs are flushed.


## CLI Flag Guide

Supported flags in `protocol/node.py`:

- `--host`
  - Local bind IP address.
  - Default: `127.0.0.1`.

- `--port` (required)
  - Local UDP port for this node.
  - must be unique per node on the same machine.

- `--bootstrap`
  - Seed node address in `ip:port` format used for discovery.
  - Default: not set (standalone node).
  - use `127.0.0.1:<port>` for localhost runs.

- `--fanout`
  - Number of random peers selected per gossip forward.
  - Default: `3`.
  - higher values increase coverage and overhead.

- `--ttl`
  - Hop limit for each gossip message.
  - Default: `8`.
  - forwarding stops when TTL reaches `0`.

- `--peer-limit`
  - Max number of peers kept in peer table.
  - Default: `20`.
  - lower values can reduce connectivity.

- `--ping-interval`
  - Heartbeat period (seconds) for sending `PING`.
  - Default: `5.0`.
  - shorter intervals increase control traffic.

- `--peer-timeout`
  - Remove peer if not seen for this many seconds.
  - Default: `15.0`.
  - should be greater than `--ping-interval`.

- `--seed`
  - Random seed for reproducible peer sampling and fanout choices.
  - Default: `42`.
  - change this to vary runs in analysis.

- `--pull-interval`
  - Enable hybrid push-pull when `> 0`.
  - Interval (seconds) between `IHAVE` broadcasts.
  - Default: `0.0` (disabled).
  - only applies when running hybrid mode.

- `--ihave-max-ids`
  - Maximum IDs advertised in each `IHAVE`.
  - Default: `32`.
  - caps control-message size.

- `--pow-k`
  - PoW difficulty for HELLO admission (`k` leading zeros in digest).
  - Default: `0` (disabled).
  - higher values slow node join.

### Recommended 2-Node Manual Test Settings

If terminal output is too noisy while typing commands, increase heartbeat spacing:

```bash
python -m protocol.node --port 9000 --fanout 3 --ttl 8 --peer-limit 20 --ping-interval 10 --peer-timeout 30 --seed 42
python -m protocol.node --port 9001 --bootstrap 127.0.0.1:9000 --fanout 3 --ttl 8 --peer-limit 20 --ping-interval 10 --peer-timeout 30 --seed 7
```

## Logging Notes

Important events are logged to stdout including:

- peer add/remove
- message send operations
- gossip receive + forwarding
- PoW mining/validation outcomes

Gossip receive log lines use this shape (for later analysis tooling):

```text
RECV msg_type=GOSSIP msg_id=<...> first_seen=<true|false> node_id=<...> recv_ms=<...> topic=<...> via=<local|ip:port>
```

## Scripts

### Simulation

Run the required simulations for $N \in \{10,20,50\}$ with 5 seeds, in both push and hybrid modes:

```bash
python -m scripts.simulate --sizes 10,20,50 --runs 5 --mode both --fanout 3 --ttl 8 --peer-limit 20 --ping-interval 5 --peer-timeout 15 --pull-interval 2 --ihave-max-ids 32
```

Logs are written under `scripts/out/<timestamp>/mode_<mode>/N<...>_seed<...>/` with one log per node.

Simulation options:

- `--sizes`
  - Comma-separated N values.
  - Default: `10,20,50`.
  - use at least three sizes for the report.
- `--runs`
  - Number of seeds per N.
  - Default: `5`.
  - must be at least 5 for the requirement.
- `--mode`
  - `push`, `hybrid`, or `both`.
  - Default: `both`.
  - run both modes to compare overhead and convergence.
- `--base-port`
  - First UDP port; nodes use sequential ports.
  - Default: `9000`.
  - avoid port conflicts with other runs.
- `--seed-start`
  - Base seed for each run.
  - Default: `100`.
  - change to vary experiment batches.
- `--startup-wait`
  - Seconds to wait before sending gossip.
  - Default: `2.0`.
  - increase for larger N to finish bootstrapping.
- `--gossip-wait`
  - Seconds to wait for propagation.
  - Default: `8.0`.
  - increase for larger N to reach 95% coverage.
- `--shutdown-wait`
  - Seconds to wait for clean shutdown.
  - Default: `2.0`.
  - keep small to avoid long test times.
- `--topic`
  - Gossip topic string.
  - Default: `news`.
- `--data`
  - Gossip payload string.
  - Default: `hello`.
- `--out-dir`
  - Root output folder.
  - Default: `scripts/out`.
  - each run creates a timestamped subfolder.
- `--python`
  - Python executable (defaults to env `PYTHON` or `python`).
  - Default: `python`.

Shared node flags used by simulation are documented in the CLI Flag Guide: `--host`, `--fanout`, `--ttl`, `--peer-limit`, `--ping-interval`, `--peer-timeout`, `--pull-interval`, `--ihave-max-ids`, `--pow-k`.

### Analysis

Parse logs, compute convergence time and message overhead, and write CSV/JSON summary:

```bash
python -m scripts.analyze --input scripts/out/<timestamp>
```

To also generate plots (requires `matplotlib`):

```bash
python -m scripts.analyze --input scripts/out/<timestamp> --plot
```

Outputs:

- `scripts/out/<timestamp>/out/runs.csv`
- `scripts/out/<timestamp>/out/summary.csv`
- `scripts/out/<timestamp>/out/summary.json`
- `scripts/out/<timestamp>/out/convergence.png` (optional)
- `scripts/out/<timestamp>/out/overhead.png` (optional)

Analysis options:

- `--input`
  - Required input folder containing run logs.
  - pass a single run folder (timestamp) for clean results.
- `--output`
  - Optional output folder.
  - Default: `<input>/out`.
- `--plot`
  - Enable PNG plot generation.

### PoW Timing

Benchmark PoW mining time for a few `pow_k` values and generate a CSV (and optional plot):

```bash
python -m scripts.pow_bench --pow-ks 2,3,4 --runs 5 --plot
```

Outputs are written under `scripts/pow/<timestamp>/`.

PoW timing options:

- `--pow-ks`
  - Comma-separated difficulty values.
  - Default: `2,3,4`.
  - pick 2 or 3 values for the report.
- `--runs`
  - Samples per difficulty.
  - Default: `5`.
  - increase for more stable averages.
- `--out-dir`
  - Root output folder.
  - Default: `scripts/pow`.
- `--plot`
  - Enable PNG plot generation.

### Correctness Check

Run a 10-node local network and verify at least 90% coverage from a single gossip:

```bash
python -m scripts.correctness --size 10 --min-coverage 0.9
```

Correctness options:

- `--size`
  - Number of nodes.
  - Default: `10`.
  - set to 10 to match the requirement.
- `--min-coverage`
  - Required coverage ratio (0-1).
  - Default: `0.9`.
- `--base-port`
  - First UDP port; nodes use sequential ports.
  - Default: `9100`.
  - avoid port conflicts with simulation runs.
- `--seed-start`
  - Base seed for nodes.
  - Default: `200`.
- `--startup-wait`
  - Seconds to wait before sending gossip.
  - Default: `2.0`.
  - increase if bootstrapping is slow.
- `--gossip-wait`
  - Seconds to wait for propagation.
  - Default: `8.0`.
  - increase if coverage is below 0.9.
- `--shutdown-wait`
  - Seconds to wait for clean shutdown.
  - Default: `2.0`.
- `--topic`
  - Gossip topic string.
  - Default: `news`.
- `--data`
  - Gossip payload string.
  - Default: `hello`.
- `--out-dir`
  - Root output folder.
  - Default: `scripts/correctness`.
- `--python`
  - Python executable.
  - Default: `python`.

Shared node flags used by correctness are documented in the CLI Flag Guide: `--host`, `--fanout`, `--ttl`, `--peer-limit`, `--ping-interval`, `--peer-timeout`, `--ihave-max-ids`, `--pow-k`.

## Run Tests

```bash
pytest -q
```
