import asyncio

from protocol import peers


class RuntimeStub:
    def __init__(self) -> None:
        self.node_id = "node-a"
        self.self_addr = "127.0.0.1:9000"
        self.config = {
            "ttl": 8,
            "peer_limit": 20,
            "ping_interval": 0.01,
            "peer_timeout": 1.0,
            "pow_k": 0,
        }
        self.local_pow = None
        self.peers: dict[str, dict] = {}
        self.stopped = asyncio.Event()
        self.ping_seq = 0
        self.sent: list[tuple[dict, str]] = []

    async def send_to_addr_str(self, addr: str, message: dict) -> None:
        self.sent.append((message, addr))

    def log(self, _message: str) -> None:
        return


def test_bootstrap_sends_hello_and_get_peers_once() -> None:
    runtime = RuntimeStub()
    runtime.config["bootstrap"] = "127.0.0.1:9001"

    asyncio.run(peers.bootstrap(runtime))

    sent_types = [str(message.get("msg_type", "")) for message, _ in runtime.sent]
    assert sent_types.count("HELLO") == 1
    assert sent_types.count("GET_PEERS") >= 1


def test_ping_loop_removes_after_three_consecutive_timeouts() -> None:
    runtime = RuntimeStub()
    runtime.peers["node-b"] = {"addr": "127.0.0.1:9001", "last_seen": 0.0, "missed_pings": 0}

    original_sleep = peers.asyncio.sleep
    original_time = peers.time.time

    sleep_calls = {"count": 0}

    async def fake_sleep(_interval: float) -> None:
        sleep_calls["count"] += 1
        if sleep_calls["count"] >= 4:
            runtime.stopped.set()

    tick = {"now": 10.0}

    def fake_time() -> float:
        current = tick["now"]
        tick["now"] += 1.1
        return current

    peers.asyncio.sleep = fake_sleep
    peers.time.time = fake_time
    try:
        asyncio.run(peers.ping_loop(runtime))
    finally:
        peers.asyncio.sleep = original_sleep
        peers.time.time = original_time

    assert "node-b" not in runtime.peers


def test_ping_loop_sends_before_first_sleep() -> None:
    runtime = RuntimeStub()
    runtime.peers["node-b"] = {"addr": "127.0.0.1:9001", "last_seen": 10.0, "missed_pings": 0}

    original_sleep = peers.asyncio.sleep

    async def fake_sleep(_interval: float) -> None:
        runtime.stopped.set()

    peers.asyncio.sleep = fake_sleep
    try:
        asyncio.run(peers.ping_loop(runtime))
    finally:
        peers.asyncio.sleep = original_sleep

    sent_types = [str(message.get("msg_type", "")) for message, _ in runtime.sent]
    assert "PING" in sent_types


def test_handle_get_peers_excludes_requester_from_list() -> None:
    runtime = RuntimeStub()
    runtime.peers = {
        "node-b": {"addr": "127.0.0.1:9001", "last_seen": 0.0, "missed_pings": 0},
        "node-c": {"addr": "127.0.0.1:9002", "last_seen": 0.0, "missed_pings": 0},
        "node-d": {"addr": "127.0.0.1:9003", "last_seen": 0.0, "missed_pings": 0},
    }

    message = {
        "sender_id": "node-b",
        "sender_addr": "127.0.0.1:9001",
        "payload": {"max_peers": 20},
    }

    asyncio.run(peers.handle_get_peers(runtime, message, ("127.0.0.1", 9001)))

    response, target_addr = runtime.sent[-1]
    assert target_addr == "127.0.0.1:9001"
    assert response["msg_type"] == "PEERS_LIST"
    listed_ids = {item["node_id"] for item in response["payload"]["peers"]}
    assert "node-b" not in listed_ids


def test_upsert_peer_refreshes_table_when_full() -> None:
    runtime = RuntimeStub()
    runtime.config["peer_limit"] = 2
    runtime.peers = {
        "node-b": {"addr": "127.0.0.1:9001", "last_seen": 100.0, "missed_pings": 0},
        "node-c": {"addr": "127.0.0.1:9002", "last_seen": 100.0, "missed_pings": 0},
    }

    original_choice = peers.random.choice

    def fake_choice(items):
        return list(items)[0]

    peers.random.choice = fake_choice
    try:
        peers.upsert_peer(runtime, "node-d", "127.0.0.1:9003")
    finally:
        peers.random.choice = original_choice

    assert len(runtime.peers) == 2
    assert "node-d" in runtime.peers
