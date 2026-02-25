import argparse
import asyncio
import contextlib
import random
import signal
import sys
import time
import uuid
from collections import deque
from dataclasses import dataclass
from typing import Any

from modules import hybrid, security
from protocol import gossip, network, peers


@dataclass
class Config:
    host: str
    port: int
    bootstrap: str | None
    fanout: int
    ttl: int
    peer_limit: int
    ping_interval: float
    peer_timeout: float
    seed: int
    pull_interval: float
    ihave_max_ids: int
    pow_k: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "host": self.host,
            "port": self.port,
            "bootstrap": self.bootstrap,
            "fanout": self.fanout,
            "ttl": self.ttl,
            "peer_limit": self.peer_limit,
            "ping_interval": self.ping_interval,
            "peer_timeout": self.peer_timeout,
            "seed": self.seed,
            "pull_interval": self.pull_interval,
            "ihave_max_ids": self.ihave_max_ids,
            "pow_k": self.pow_k,
        }


class NodeRuntime:
    def __init__(self, config: Config):
        self.config = config.as_dict()
        self.node_id = str(uuid.uuid4())
        self.self_addr = f"{config.host}:{config.port}"
        self.peers: dict[str, dict[str, Any]] = {}
        self.seen_set: set[str] = set()
        self.seen_order: deque[str] = deque(maxlen=10000)
        self.message_cache: dict[str, dict[str, Any]] = {}
        self.ping_seq = 0
        self.sent_count = 0
        self.transport: asyncio.DatagramTransport | None = None
        self.tasks: list[asyncio.Task] = []
        self.stopped = asyncio.Event()
        self.local_pow: dict[str, Any] | None = None
        self.ui_mode = "logs"
        self.buffered_logs: deque[str] = deque(maxlen=500)
        self.message_events: deque[dict[str, Any]] = deque(maxlen=2000)

    def log(self, message: str) -> None:
        ts = int(time.time() * 1000)
        line = f"[{ts}] node={self.node_id[:8]} {message}"
        if self.ui_mode == "logs":
            print(line, flush=True)
            return
        self.buffered_logs.append(line)

    def ui_print(self, message: str) -> None:
        ts = int(time.time() * 1000)
        print(f"[{ts}] node={self.node_id[:8]} {message}", flush=True)

    def set_ui_mode(self, mode: str) -> None:
        if mode not in {"logs", "command"}:
            self.ui_print(f"Unknown mode '{mode}'. Use 'logs' or 'command'.")
            return

        if mode == self.ui_mode:
            self.ui_print(f"Mode unchanged: {mode}")
            return

        previous = self.ui_mode
        self.ui_mode = mode

        if previous == "command" and mode == "logs":
            self.ui_print(f"Switched to logs mode. Flushing {len(self.buffered_logs)} buffered log(s).")
            while self.buffered_logs:
                print(self.buffered_logs.popleft(), flush=True)
            return

        if mode == "command":
            self.ui_print("Switched to command mode. Background logs are buffered.")

    def track_message_event(
        self,
        message: dict[str, Any],
        *,
        first_seen: bool,
        source_addr: tuple[str, int] | None,
    ) -> None:
        payload = message.get("payload", {})
        if not isinstance(payload, dict):
            payload = {}

        source = "local" if source_addr is None else f"{source_addr[0]}:{source_addr[1]}"
        self.message_events.append(
            {
                "at_ms": int(time.time() * 1000),
                "msg_id": str(message.get("msg_id", "")),
                "topic": str(payload.get("topic", "")),
                "origin_id": str(payload.get("origin_id", "")),
                "sender_id": str(message.get("sender_id", "")),
                "ttl": int(message.get("ttl", 0)) if isinstance(message.get("ttl"), int) else 0,
                "first_seen": first_seen,
                "source": source,
            }
        )

    def print_message_events(self, limit: int = 20) -> None:
        if not self.message_events:
            self.ui_print("MESSAGES count=0")
            return

        bounded_limit = max(1, min(limit, 200))
        selected = list(self.message_events)[-bounded_limit:]
        self.ui_print(
            f"MESSAGES total_events={len(self.message_events)} showing_last={len(selected)} "
            "(first_seen=true means first time this node saw that msg_id)"
        )
        for event in selected:
            self.ui_print(
                "MSG_EVENT "
                f"first_seen={str(event['first_seen']).lower()} "
                f"msg_id={event['msg_id']} "
                f"topic={event['topic']} "
                f"origin={event['origin_id'][:8]} "
                f"sender={event['sender_id'][:8]} "
                f"source={event['source']} "
                f"ttl={event['ttl']} "
                f"at_ms={event['at_ms']}"
            )

    async def start(self) -> None:
        loop = asyncio.get_running_loop()
        await loop.create_datagram_endpoint(
            lambda: network.GossipDatagramProtocol(self),
            local_addr=(self.config["host"], self.config["port"]),
        )

        if self.config["pow_k"] > 0:
            self.log(f"Mining startup PoW difficulty={self.config['pow_k']}")
            self.local_pow = await security.mine_pow_async(self.node_id, self.config["pow_k"])
            self.log(f"PoW ready nonce={self.local_pow['nonce']}")

        self.tasks.append(asyncio.create_task(peers.ping_loop(self), name="ping_loop"))
        self.tasks.append(asyncio.create_task(self.user_input_loop(), name="input_loop"))

        if self.config["pull_interval"] > 0:
            self.tasks.append(asyncio.create_task(hybrid.pull_loop(self), name="pull_loop"))

        await peers.bootstrap(self)

    async def stop(self) -> None:
        if self.stopped.is_set():
            return

        self.stopped.set()
        for task in self.tasks:
            task.cancel()

        for task in self.tasks:
            with contextlib.suppress(asyncio.CancelledError):
                await task

        if self.transport is not None:
            self.transport.close()

    async def handle_message(self, message: dict[str, Any], addr: tuple[str, int]) -> None:
        msg_type = message.get("msg_type")

        sender_id = message.get("sender_id")
        sender_addr = message.get("sender_addr")
        if isinstance(sender_id, str) and isinstance(sender_addr, str):
            peers.upsert_peer(self, sender_id, sender_addr)

        if msg_type == "HELLO":
            await peers.handle_hello(self, message, addr)
        elif msg_type == "GET_PEERS":
            await peers.handle_get_peers(self, message, addr)
        elif msg_type == "PEERS_LIST":
            await peers.handle_peers_list(self, message, addr)
        elif msg_type == "PING":
            await peers.handle_ping(self, message, addr)
        elif msg_type == "PONG":
            await peers.handle_pong(self, message, addr)
        elif msg_type == "GOSSIP":
            await gossip.handle_gossip(self, message, addr)
        elif msg_type == "IHAVE" and self.config["pull_interval"] > 0:
            await hybrid.handle_ihave(self, message, addr)
        elif msg_type == "IWANT" and self.config["pull_interval"] > 0:
            await hybrid.handle_iwant(self, message, addr)

    async def send_to_peer(self, node_id: str, message: dict[str, Any]) -> None:
        peer = self.peers.get(node_id)
        if not peer:
            return
        await self.send_to_addr_str(peer["addr"], message)

    async def send_to_addr_str(self, addr_str: str, message: dict[str, Any]) -> None:
        if self.transport is None:
            return
        try:
            ip, port = peers.parse_addr(addr_str)
        except Exception:
            self.log(f"Invalid address skipped: {addr_str}")
            return

        await network.send_message(self.transport, ip, port, message)
        self.sent_count += 1
        self.log(f"SEND msg_type={message.get('msg_type')} msg_id={message.get('msg_id')} to={addr_str}")

    async def user_input_loop(self) -> None:
        help_text = (
            "Commands: gossip <topic> <text> | peers | stats | messages [limit] | help | quit \n"
            "if you want to stop logs use '/' to toggle mode. (plain text is ignored)"
        )
        self.ui_print(help_text)

        while not self.stopped.is_set():
            try:
                prompt = "cmd> " if self.ui_mode == "command" else ""
                line = await asyncio.to_thread(input, prompt)
            except (EOFError, KeyboardInterrupt):
                await self.stop()
                return

            command = line.strip()
            if not command:
                continue

            if command == "/":
                next_mode = "command" if self.ui_mode == "logs" else "logs"
                self.set_ui_mode(next_mode)
                continue
            if command == "help":
                self.ui_print(help_text)
                continue
            if command.startswith("mode "):
                target_mode = command.split(maxsplit=1)[1].strip()
                self.set_ui_mode(target_mode)
                continue
            if command == "peers":
                snapshot = [f"{node_id[:8]}@{p['addr']}" for node_id, p in self.peers.items()]
                self.ui_print(f"PEERS count={len(snapshot)} list={snapshot}")
                continue
            if command == "stats":
                self.ui_print(f"STATS peers={len(self.peers)} seen={len(self.seen_set)} sent={self.sent_count}")
                continue
            if command == "messages":
                self.print_message_events()
                continue
            if command.startswith("messages "):
                limit_str = command.split(maxsplit=1)[1].strip()
                try:
                    limit = int(limit_str)
                except ValueError:
                    self.ui_print("Usage: messages [limit] (limit must be an integer)")
                    continue
                self.print_message_events(limit)
                continue
            if command == "quit":
                await self.stop()
                return

            if command.startswith("gossip "):
                parts = command.split(maxsplit=2)
                if len(parts) < 3:
                    self.ui_print("Usage: gossip <topic> <text>")
                    continue
                topic, data = parts[1], parts[2]
            else:
                self.ui_print("Unknown command. Use help. Plain text does not publish gossip.")
                continue

            msg_id = await gossip.publish_gossip(self, topic, data)
            self.ui_print(f"GOSSIP msg_id={msg_id} topic={topic}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Async UDP Gossip Node")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--bootstrap", type=str, default=None, help="bootstrap addr as ip:port")
    parser.add_argument("--fanout", type=int, default=3)
    parser.add_argument("--ttl", type=int, default=8)
    parser.add_argument("--peer-limit", type=int, default=20)
    parser.add_argument("--ping-interval", type=float, default=30.0)
    parser.add_argument("--peer-timeout", type=float, default=15.0)
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--pull-interval", type=float, default=0.0)
    parser.add_argument("--ihave-max-ids", type=int, default=32)
    parser.add_argument("--pow-k", type=int, default=0)
    return parser


async def run(args: argparse.Namespace) -> None:
    runtime_seed = args.seed if args.seed is not None else random.SystemRandom().randrange(0, 2**31)
    random.seed(runtime_seed)
    config = Config(
        host=args.host,
        port=args.port,
        bootstrap=args.bootstrap,
        fanout=max(1, args.fanout),
        ttl=max(1, args.ttl),
        peer_limit=max(1, args.peer_limit),
        ping_interval=max(0.2, args.ping_interval),
        peer_timeout=max(args.ping_interval, args.peer_timeout),
        seed=runtime_seed,
        pull_interval=max(0.0, args.pull_interval),
        ihave_max_ids=max(1, args.ihave_max_ids),
        pow_k=max(0, args.pow_k),
    )
    runtime = NodeRuntime(config)
    runtime.log(f"Runtime random seed={runtime_seed}")

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        with contextlib.suppress(NotImplementedError):
            loop.add_signal_handler(sig, lambda: asyncio.create_task(runtime.stop()))

    await runtime.start()
    await runtime.stopped.wait()


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    try:
        asyncio.run(run(args))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
