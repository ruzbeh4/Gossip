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
- Optional periodic peer discovery refresh via `GET_PEERS`
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

## Required CLI Parameters

Supported flags in `protocol/node.py`:

- `--port`
- `--bootstrap` (`ip:port`)
- `--fanout`
- `--ttl`
- `--peer-limit`
- `--ping-interval`
- `--peer-timeout`
- `--peer-refresh-interval`
- `--seed`
- `--pull-interval`
- `--ihave-max-ids`
- `--pow-k`

## CLI Flag Guide

- `--host`
  - Local bind IP address.
  - Default: `127.0.0.1`

- `--port` (required)
  - Local UDP port for this node.

- `--bootstrap`
  - Seed node address in `ip:port` format used for discovery.
  - Default: not set (standalone node)

- `--fanout`
  - Number of random peers selected per gossip forward.
  - Default: `3`

- `--ttl`
  - Hop limit for each gossip message.
  - Forwarding stops when TTL reaches `0`.
  - Default: `8`

- `--peer-limit`
  - Max number of peers kept in peer table.
  - Default: `20`

- `--ping-interval`
  - Heartbeat period (seconds) for sending `PING`.
  - This is where ping/pong frequency is configured.
  - Default: `5.0`

- `--peer-timeout`
  - Remove peer if not seen for this many seconds.
  - Should be greater than `--ping-interval`.
  - Default: `15.0`

- `--peer-refresh-interval`
  - Periodic interval (seconds) to request fresh peers from random neighbors.
  - Set to `0` to disable.
  - Default: `0.0`

- `--seed`
  - Random seed for reproducible peer sampling/fanout choices.
  - Default: `42`

- `--pull-interval`
  - Enable hybrid push-pull when `> 0`.
  - Interval (seconds) between `IHAVE` broadcasts.
  - Default: `0.0` (disabled)

- `--ihave-max-ids`
  - Maximum IDs advertised in each `IHAVE`.
  - Default: `32`

- `--pow-k`
  - PoW difficulty for HELLO admission (`k` leading zeros in digest).
  - Default: `0` (disabled)

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
python -m scripts.simulate --sizes 10,20,50 --runs 5 --mode both \
	--fanout 3 --ttl 8 --peer-limit 20 --ping-interval 5 --peer-timeout 15 \
	--pull-interval 2 --ihave-max-ids 32
```

Logs are written under `scripts/out/<timestamp>/mode_<mode>/N<...>_seed<...>/` with one log per node.

For larger N, consider enabling periodic peer refresh to improve connectivity:

```bash
python -m scripts.simulate --sizes 10,20,50 --runs 5 --mode both --peer-refresh-interval 6
```

### Analysis

Parse logs, compute convergence time and message overhead, and write CSV/JSON summary:

```bash
python -m scripts.analyze --input scripts/out --output scripts/results
```

To also generate plots (requires `matplotlib`):

```bash
python -m scripts.analyze --input scripts/out --output scripts/results --plot
```

Outputs:

- `scripts/results/runs.csv`
- `scripts/results/summary.csv`
- `scripts/results/summary.json`
- `scripts/results/convergence.png` (optional)
- `scripts/results/overhead.png` (optional)

### Correctness Check

Run a 10-node local network and verify at least 90% coverage from a single gossip:

```bash
python -m scripts.correctness --size 10 --min-coverage 0.9
```

## Run Tests

```bash
pytest -q
```
