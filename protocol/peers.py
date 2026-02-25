import asyncio
import random
import time
from typing import TYPE_CHECKING

from modules import security
from protocol import messages

if TYPE_CHECKING:
    from protocol.node import NodeRuntime


def parse_addr(addr: str) -> tuple[str, int]:
    ip, port_str = addr.rsplit(":", 1)
    return ip, int(port_str)


def addr_to_str(addr: tuple[str, int]) -> str:
    return f"{addr[0]}:{addr[1]}"


def upsert_peer(runtime: "NodeRuntime", node_id: str, peer_addr: str) -> None:
    now = time.time()
    if node_id == runtime.node_id:
        return

    if node_id in runtime.peers:
        runtime.peers[node_id]["addr"] = peer_addr
        runtime.peers[node_id]["last_seen"] = now
        return

    if len(runtime.peers) >= runtime.config["peer_limit"]:
        runtime.log(f"Peer limit reached, ignoring peer node_id={node_id} addr={peer_addr}")
        return

    runtime.peers[node_id] = {"addr": peer_addr, "last_seen": now}
    runtime.log(f"Peer added node_id={node_id} addr={peer_addr}")


async def bootstrap(runtime: "NodeRuntime") -> None:
    bootstrap_addr = runtime.config.get("bootstrap")
    if not bootstrap_addr:
        return

    hello = messages.build_hello(
        sender_id=runtime.node_id,
        sender_addr=runtime.self_addr,
        ttl=runtime.config["ttl"],
        pow_payload=runtime.local_pow,
    )
    await runtime.send_to_addr_str(bootstrap_addr, hello)

    get_peers = messages.build_get_peers(
        sender_id=runtime.node_id,
        sender_addr=runtime.self_addr,
        ttl=runtime.config["ttl"],
        max_peers=runtime.config["peer_limit"],
    )
    await runtime.send_to_addr_str(bootstrap_addr, get_peers)
    runtime.log(f"Bootstrap initiated via {bootstrap_addr}")


async def handle_hello(runtime: "NodeRuntime", message: dict, addr: tuple[str, int]) -> None:
    sender_id = message.get("sender_id", "")
    sender_addr = message.get("sender_addr") or addr_to_str(addr)

    if runtime.config["pow_k"] > 0:
        pow_payload = message.get("payload", {}).get("pow")
        if not security.verify_pow(sender_id, pow_payload, runtime.config["pow_k"]):
            runtime.log(f"Rejected HELLO from node_id={sender_id} due to invalid PoW")
            return

    upsert_peer(runtime, sender_id, sender_addr)


async def handle_get_peers(runtime: "NodeRuntime", message: dict, addr: tuple[str, int]) -> None:
    max_peers = int(message.get("payload", {}).get("max_peers", runtime.config["peer_limit"]))
    sender_addr = message.get("sender_addr") or addr_to_str(addr)

    peer_items = list(runtime.peers.items())
    random.shuffle(peer_items)
    selected = peer_items[: max(0, min(max_peers, runtime.config["peer_limit"]))]

    payload = [{"node_id": node_id, "addr": data["addr"]} for node_id, data in selected]
    if len(payload) < max_peers:
        payload.append({"node_id": runtime.node_id, "addr": runtime.self_addr})

    response = messages.build_peers_list(
        sender_id=runtime.node_id,
        sender_addr=runtime.self_addr,
        ttl=runtime.config["ttl"],
        peers=payload,
    )
    await runtime.send_to_addr_str(sender_addr, response)


async def handle_peers_list(runtime: "NodeRuntime", message: dict, _addr: tuple[str, int]) -> None:
    peers_payload = message.get("payload", {}).get("peers", [])
    if not isinstance(peers_payload, list):
        return

    for item in peers_payload:
        node_id = item.get("node_id")
        peer_addr = item.get("addr")
        if isinstance(node_id, str) and isinstance(peer_addr, str):
            upsert_peer(runtime, node_id, peer_addr)


async def handle_ping(runtime: "NodeRuntime", message: dict, addr: tuple[str, int]) -> None:
    sender_id = message.get("sender_id", "")
    sender_addr = message.get("sender_addr") or addr_to_str(addr)
    upsert_peer(runtime, sender_id, sender_addr)

    payload = message.get("payload", {})
    ping_id = str(payload.get("ping_id", ""))
    seq = int(payload.get("seq", 0))

    pong = messages.build_pong(
        sender_id=runtime.node_id,
        sender_addr=runtime.self_addr,
        ttl=runtime.config["ttl"],
        ping_id=ping_id,
        seq=seq,
    )
    await runtime.send_to_addr_str(sender_addr, pong)


async def handle_pong(runtime: "NodeRuntime", message: dict, addr: tuple[str, int]) -> None:
    sender_id = message.get("sender_id", "")
    sender_addr = message.get("sender_addr") or addr_to_str(addr)
    upsert_peer(runtime, sender_id, sender_addr)


async def ping_loop(runtime: "NodeRuntime") -> None:
    while not runtime.stopped.is_set():
        await asyncio.sleep(runtime.config["ping_interval"])
        now = time.time()

        peers_snapshot = list(runtime.peers.items())
        for _node_id, data in peers_snapshot:
            ping_id = messages.new_msg_id()
            runtime.ping_seq += 1
            ping = messages.build_ping(
                sender_id=runtime.node_id,
                sender_addr=runtime.self_addr,
                ttl=runtime.config["ttl"],
                ping_id=ping_id,
                seq=runtime.ping_seq,
            )
            await runtime.send_to_addr_str(data["addr"], ping)

        dead_nodes: list[str] = []
        for node_id, data in runtime.peers.items():
            if now - float(data["last_seen"]) > runtime.config["peer_timeout"]:
                dead_nodes.append(node_id)

        for node_id in dead_nodes:
            old_addr = runtime.peers[node_id]["addr"]
            del runtime.peers[node_id]
            runtime.log(f"Peer removed node_id={node_id} addr={old_addr} reason=timeout")
