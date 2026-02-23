import asyncio
import random
from typing import TYPE_CHECKING

from protocol import messages

if TYPE_CHECKING:
    from protocol.node import NodeRuntime


async def pull_loop(runtime: "NodeRuntime") -> None:
    while not runtime.stopped.is_set():
        await asyncio.sleep(runtime.config["pull_interval"])

        if not runtime.peers or not runtime.seen_order:
            continue

        peer_ids = list(runtime.peers.keys())
        sample_size = min(runtime.config["fanout"], len(peer_ids))
        if sample_size <= 0:
            continue

        selected_peers = random.sample(peer_ids, sample_size)
        ids = list(runtime.seen_order)[-runtime.config["ihave_max_ids"] :]

        for peer_id in selected_peers:
            ihave = messages.build_ihave(
                sender_id=runtime.node_id,
                sender_addr=runtime.self_addr,
                ttl=runtime.config["ttl"],
                ids=ids,
                max_ids=runtime.config["ihave_max_ids"],
            )
            await runtime.send_to_peer(peer_id, ihave)


async def handle_ihave(runtime: "NodeRuntime", message: dict, _addr: tuple[str, int]) -> None:
    advertised = message.get("payload", {}).get("ids", [])
    if not isinstance(advertised, list):
        return

    missing = [mid for mid in advertised if isinstance(mid, str) and mid not in runtime.seen_set]
    if not missing:
        return

    sender_addr = message.get("sender_addr")
    if not isinstance(sender_addr, str):
        return

    iwant = messages.build_iwant(
        sender_id=runtime.node_id,
        sender_addr=runtime.self_addr,
        ttl=runtime.config["ttl"],
        ids=missing,
    )
    await runtime.send_to_addr_str(sender_addr, iwant)


async def handle_iwant(runtime: "NodeRuntime", message: dict, _addr: tuple[str, int]) -> None:
    ids = message.get("payload", {}).get("ids", [])
    if not isinstance(ids, list):
        return

    sender_addr = message.get("sender_addr")
    if not isinstance(sender_addr, str):
        return

    for msg_id in ids:
        if not isinstance(msg_id, str):
            continue
        cached = runtime.message_cache.get(msg_id)
        if not cached:
            continue
        await runtime.send_to_addr_str(sender_addr, cached)
