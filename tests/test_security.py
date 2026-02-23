from modules import security


def test_pow_mine_and_verify() -> None:
    node_id = "node-test"
    result = security.mine_pow(node_id, 2)
    assert security.verify_pow(node_id, result, 2)


def test_pow_verify_rejects_tampered_nonce() -> None:
    node_id = "node-test"
    result = security.mine_pow(node_id, 2)
    result["nonce"] = int(result["nonce"]) + 1
    assert not security.verify_pow(node_id, result, 2)
