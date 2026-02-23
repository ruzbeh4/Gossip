from protocol import messages


def test_build_and_parse_gossip_message() -> None:
    payload = messages.build_gossip(
        sender_id="node-a",
        sender_addr="127.0.0.1:8000",
        ttl=8,
        topic="news",
        data="hello",
        origin_id="node-a",
        origin_timestamp_ms=1000,
    )
    parsed = messages.parse_message(messages.encode_message(payload).decode("utf-8"))
    assert parsed["msg_type"] == "GOSSIP"
    assert parsed["payload"]["topic"] == "news"
    assert parsed["ttl"] == 8


def test_parse_invalid_json_raises() -> None:
    try:
        messages.parse_message("not-json")
        assert False, "expected ValueError"
    except ValueError:
        assert True
