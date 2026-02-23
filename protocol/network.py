import asyncio
from typing import Any

from protocol import messages


class GossipDatagramProtocol(asyncio.DatagramProtocol):
    def __init__(self, runtime: Any):
        self.runtime = runtime
        self.transport: asyncio.DatagramTransport | None = None

    def connection_made(self, transport: asyncio.BaseTransport) -> None:
        self.transport = transport  # type: ignore[assignment]
        self.runtime.transport = self.transport
        self.runtime.log("UDP endpoint ready")

    def datagram_received(self, data: bytes, addr: tuple[str, int]) -> None:
        try:
            raw = data.decode("utf-8")
        except UnicodeDecodeError:
            self.runtime.log(f"Dropped non-UTF8 datagram from {addr[0]}:{addr[1]}")
            return

        try:
            parsed = messages.parse_message(raw)
        except ValueError as exc:
            self.runtime.log(f"Dropped invalid message from {addr[0]}:{addr[1]}: {exc}")
            return

        asyncio.create_task(self.runtime.handle_message(parsed, addr))

    def error_received(self, exc: Exception) -> None:
        self.runtime.log(f"Datagram error: {exc}")

    def connection_lost(self, exc: Exception | None) -> None:
        if exc:
            self.runtime.log(f"UDP connection lost with error: {exc}")
        else:
            self.runtime.log("UDP connection closed")


async def send_message(
    transport: asyncio.DatagramTransport,
    target_ip: str,
    target_port: int,
    message: dict[str, Any],
) -> None:
    packet = messages.encode_message(message)
    transport.sendto(packet, (target_ip, target_port))
