from collections.abc import AsyncGenerator, Awaitable, Callable
from typing import cast

from redis.asyncio import Redis
from taskiq import AckableMessage
from taskiq_redis import RedisStreamBroker

from src.core.config import RedisConfig

TASK_LEASE_SECONDS = 120


class MailStreamBroker(RedisStreamBroker):
    """Recover pending mail even when the stream has no new messages."""

    async def listen(self) -> AsyncGenerator[AckableMessage]:
        cursor: bytes | str = "0-0"
        async with Redis(connection_pool=self.connection_pool) as redis:
            while True:
                # Taskiq Redis 1.2.4 only attempts recovery after reading new messages.
                cursor, pending, _ = cast(
                    tuple[bytes, list[tuple[bytes, dict[bytes, bytes]]], list[bytes]],
                    await redis.xautoclaim(
                        self.queue_name,
                        self.consumer_group_name,
                        self.consumer_name,
                        self.idle_timeout,
                        start_id=cursor,
                        count=1,
                    ),
                )
                for message_id, message in pending:
                    yield AckableMessage(data=message[b"data"], ack=self._ack_message(message_id))

                streams = cast(
                    list[tuple[bytes, list[tuple[bytes, dict[bytes, bytes]]]]],
                    await redis.xreadgroup(
                        self.consumer_group_name,
                        self.consumer_name,
                        {self.queue_name: ">"},
                        count=1,
                        block=self.block,
                    ),
                )
                for _, messages in streams:
                    for message_id, message in messages:
                        yield AckableMessage(
                            data=message[b"data"], ack=self._ack_message(message_id)
                        )

    def _ack_message(self, message_id: bytes) -> Callable[[], Awaitable[None]]:
        async def acknowledge() -> None:
            # This stream is dedicated to a single consumer group.
            async with Redis(connection_pool=self.connection_pool) as redis:
                await redis.eval(
                    "redis.call('XACK', KEYS[1], ARGV[1], ARGV[2]); "
                    "return redis.call('XDEL', KEYS[1], ARGV[2])",
                    1,
                    self.queue_name,
                    self.consumer_group_name,
                    message_id,
                )

        return acknowledge


def build_broker(redis: RedisConfig) -> MailStreamBroker:
    return MailStreamBroker(
        url=redis.url,
        queue_name=f"{redis.key_prefix}:auth:mail",
        consumer_group_name="auth-mail",
        consumer_id="0-0",
        idle_timeout=TASK_LEASE_SECONDS * 1000,
        xread_block=1000,
        max_connection_pool_size=max(2, redis.max_connections),
        socket_connect_timeout=redis.socket_timeout,
        socket_timeout=max(2.0, redis.socket_timeout),
    )
