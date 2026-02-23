import json
import time
import uuid
from typing import Any


REQUIRED_FIELDS = {
    "version",
    "msg_id",
    "msg_type",
    "sender_id",
    "sender_addr",
    "timestamp_ms",
    "ttl",
    "payload",
}


def now_ms() -> int:
    return int(time.time() * 1000)


def new_msg_id() -> str:
    return str(uuid.uuid4())


def encode_message(message: dict[str, Any]) -> bytes:
    return json.dumps(message, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def parse_message(raw: str) -> dict[str, Any]:
    try:
        message = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError("Invalid JSON") from exc

    if not isinstance(message, dict):
        raise ValueError("Message must be a JSON object")

    missing = REQUIRED_FIELDS - set(message.keys())
    if missing:
        raise ValueError(f"Missing fields: {sorted(missing)}")

    if not isinstance(message["payload"], dict):
        raise ValueError("payload must be an object")

    if not isinstance(message["ttl"], int):
        raise ValueError("ttl must be int")

    return message


def base_message(
    *,
    msg_type: str,
    sender_id: str,
    sender_addr: str,
    ttl: int,
    payload: dict[str, Any],
    msg_id: str | None = None,
) -> dict[str, Any]:
    return {
        "version": 1,
        "msg_id": msg_id or new_msg_id(),
        "msg_type": msg_type,
        "sender_id": sender_id,
        "sender_addr": sender_addr,
        "timestamp_ms": now_ms(),
        "ttl": ttl,
        "payload": payload,
    }


def build_hello(sender_id: str, sender_addr: str, ttl: int, pow_payload: dict[str, Any] | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {"capabilities": ["udp", "json"]}
    if pow_payload is not None:
        payload["pow"] = pow_payload
    return base_message(msg_type="HELLO", sender_id=sender_id, sender_addr=sender_addr, ttl=ttl, payload=payload)


def build_get_peers(sender_id: str, sender_addr: str, ttl: int, max_peers: int) -> dict[str, Any]:
    return base_message(
        msg_type="GET_PEERS",
        sender_id=sender_id,
        sender_addr=sender_addr,
        ttl=ttl,
        payload={"max_peers": max_peers},
    )


def build_peers_list(sender_id: str, sender_addr: str, ttl: int, peers: list[dict[str, str]]) -> dict[str, Any]:
    return base_message(msg_type="PEERS_LIST", sender_id=sender_id, sender_addr=sender_addr, ttl=ttl, payload={"peers": peers})


def build_gossip(
    sender_id: str,
    sender_addr: str,
    ttl: int,
    *,
    topic: str,
    data: str,
    origin_id: str,
    origin_timestamp_ms: int,
    msg_id: str | None = None,
) -> dict[str, Any]:
    return base_message(
        msg_type="GOSSIP",
        sender_id=sender_id,
        sender_addr=sender_addr,
        ttl=ttl,
        payload={
            "topic": topic,
            "data": data,
            "origin_id": origin_id,
            "origin_timestamp_ms": origin_timestamp_ms,
        },
        msg_id=msg_id,
    )


def build_ping(sender_id: str, sender_addr: str, ttl: int, ping_id: str, seq: int) -> dict[str, Any]:
    return base_message(
        msg_type="PING",
        sender_id=sender_id,
        sender_addr=sender_addr,
        ttl=ttl,
        payload={"ping_id": ping_id, "seq": seq},
    )


def build_pong(sender_id: str, sender_addr: str, ttl: int, ping_id: str, seq: int) -> dict[str, Any]:
    return base_message(
        msg_type="PONG",
        sender_id=sender_id,
        sender_addr=sender_addr,
        ttl=ttl,
        payload={"ping_id": ping_id, "seq": seq},
    )


def build_ihave(sender_id: str, sender_addr: str, ttl: int, ids: list[str], max_ids: int) -> dict[str, Any]:
    return base_message(
        msg_type="IHAVE",
        sender_id=sender_id,
        sender_addr=sender_addr,
        ttl=ttl,
        payload={"ids": ids[:max_ids], "max_ids": max_ids},
    )


def build_iwant(sender_id: str, sender_addr: str, ttl: int, ids: list[str]) -> dict[str, Any]:
    return base_message(
        msg_type="IWANT",
        sender_id=sender_id,
        sender_addr=sender_addr,
        ttl=ttl,
        payload={"ids": ids},
    )
