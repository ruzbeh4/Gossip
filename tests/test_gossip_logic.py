import asyncio
from collections import deque

from protocol import gossip, messages


class RuntimeStub:
    def __init__(self) -> None:
        self.node_id = "node-a"
        self.self_addr = "127.0.0.1:8000"
        self.config = {"ttl": 3, "fanout": 2}
        self.peers = {
            "node-b": {"addr": "127.0.0.1:8001", "last_seen": 0},
            "node-c": {"addr": "127.0.0.1:8002", "last_seen": 0},
        }
        self.seen_set = set()
        self.seen_order = deque(maxlen=100)
        self.message_cache = {}
        self.sent: list[tuple[str, str]] = []
        self.events: list[tuple[str, bool]] = []

    async def send_to_peer(self, node_id: str, message: dict) -> None:
        self.sent.append((node_id, str(message["msg_id"])))

    def log(self, _message: str) -> None:
        return

    def track_message_event(self, message: dict, *, first_seen: bool, source_addr: tuple[str, int] | None) -> None:
        _ = source_addr
        self.events.append((str(message["msg_id"]), first_seen))


def test_gossip_processed_once() -> None:
    runtime = RuntimeStub()
    event = messages.build_gossip(
        sender_id="origin",
        sender_addr="127.0.0.1:7000",
        ttl=3,
        topic="x",
        data="y",
        origin_id="origin",
        origin_timestamp_ms=0,
    )
    asyncio.run(gossip.handle_gossip(runtime, event, None))
    first_send_count = len(runtime.sent)

    echoed = dict(event)
    echoed["sender_id"] = "node-b"
    echoed["sender_addr"] = "127.0.0.1:8001"
    asyncio.run(gossip.handle_gossip(runtime, echoed, ("127.0.0.1", 8001)))

    assert len(runtime.seen_set) == 1
    assert len(runtime.sent) == first_send_count
    assert runtime.events == [(str(event["msg_id"]), True), (str(event["msg_id"]), False)]
