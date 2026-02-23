import copy
import random
from typing import TYPE_CHECKING

from protocol import messages

if TYPE_CHECKING:
    from protocol.node import NodeRuntime


async def handle_gossip(runtime: "NodeRuntime", message: dict, _addr: tuple[str, int] | None) -> None:
    msg_id = str(message.get("msg_id", ""))
    if not msg_id:
        return

    is_first_seen = msg_id not in runtime.seen_set
    runtime.track_message_event(message, first_seen=is_first_seen, source_addr=_addr)
    via = "local" if _addr is None else f"{_addr[0]}:{_addr[1]}"

    if not is_first_seen:
        runtime.log(f"RECV msg_type=GOSSIP msg_id={msg_id} first_seen=false via={via}")
        return

    runtime.seen_set.add(msg_id)
    runtime.seen_order.append(msg_id)
    runtime.message_cache[msg_id] = _cacheable_copy(runtime, message)

    recv_ms = messages.now_ms()
    runtime.log(
        f"RECV msg_type=GOSSIP msg_id={msg_id} first_seen=true node_id={runtime.node_id} recv_ms={recv_ms} "
        f"topic={message.get('payload', {}).get('topic', '')} via={via}"
    )

    next_ttl = int(message.get("ttl", 0)) - 1
    if next_ttl <= 0:
        return

    sender_id = str(message.get("sender_id", ""))
    candidate_nodes = [node_id for node_id in runtime.peers.keys() if node_id != sender_id]
    if not candidate_nodes:
        return

    fanout = min(runtime.config["fanout"], len(candidate_nodes))
    selected = random.sample(candidate_nodes, fanout)
    for node_id in selected:
        forwarded = copy.deepcopy(message)
        forwarded["sender_id"] = runtime.node_id
        forwarded["sender_addr"] = runtime.self_addr
        forwarded["timestamp_ms"] = messages.now_ms()
        forwarded["ttl"] = next_ttl
        await runtime.send_to_peer(node_id, forwarded)


def _cacheable_copy(runtime: "NodeRuntime", message: dict) -> dict:
    cached = copy.deepcopy(message)
    cached["sender_id"] = runtime.node_id
    cached["sender_addr"] = runtime.self_addr
    cached["ttl"] = runtime.config["ttl"]
    cached["timestamp_ms"] = messages.now_ms()
    return cached


async def publish_gossip(runtime: "NodeRuntime", topic: str, data: str) -> str:
    event = messages.build_gossip(
        sender_id=runtime.node_id,
        sender_addr=runtime.self_addr,
        ttl=runtime.config["ttl"],
        topic=topic,
        data=data,
        origin_id=runtime.node_id,
        origin_timestamp_ms=messages.now_ms(),
    )
    await handle_gossip(runtime, event, None)
    return str(event["msg_id"])
