import asyncio
import hashlib
from typing import Any


def _digest(node_id: str, nonce: int) -> str:
    raw = f"{node_id}{nonce}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def mine_pow(node_id: str, pow_k: int) -> dict[str, Any]:
    if pow_k <= 0:
        return {
            "hash_alg": "sha256",
            "difficulty_k": 0,
            "nonce": 0,
            "digest_hex": _digest(node_id, 0),
        }

    prefix = "0" * pow_k
    nonce = 0
    while True:
        digest = _digest(node_id, nonce)
        if digest.startswith(prefix):
            return {
                "hash_alg": "sha256",
                "difficulty_k": pow_k,
                "nonce": nonce,
                "digest_hex": digest,
            }
        nonce += 1


async def mine_pow_async(node_id: str, pow_k: int) -> dict[str, Any]:
    return await asyncio.to_thread(mine_pow, node_id, pow_k)


def verify_pow(node_id: str, pow_dict: dict[str, Any] | None, pow_k: int) -> bool:
    if pow_k <= 0:
        return True

    if not isinstance(pow_dict, dict):
        return False

    try:
        hash_alg = str(pow_dict["hash_alg"])
        difficulty_k = int(pow_dict["difficulty_k"])
        nonce = int(pow_dict["nonce"])
        digest_hex = str(pow_dict["digest_hex"])
    except (KeyError, ValueError, TypeError):
        return False

    if hash_alg.lower() != "sha256":
        return False
    if difficulty_k != pow_k:
        return False

    expected = _digest(node_id, nonce)
    if expected != digest_hex:
        return False
    if not digest_hex.startswith("0" * pow_k):
        return False
    return True
