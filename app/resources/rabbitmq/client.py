from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

import aio_pika
from aio_pika import DeliveryMode, ExchangeType, Message
from aio_pika.abc import (
    AbstractIncomingMessage,
    AbstractQueue,
    AbstractRobustChannel,
    AbstractRobustConnection,
)

from app.resources.rabbitmq.codec import encode_json_message

logger = logging.getLogger(__name__)

MessageHandler = Callable[[AbstractIncomingMessage], Awaitable[None]]


@dataclass(frozen=True)
class QueueBinding:
    exchange_name: str
    queue_name: str
    routing_key: str


class RabbitMQClient:
    def __init__(
        self,
        *,
        url: str,
        prefetch_count: int = 1,
        declare_passive: bool = True,
    ) -> None:
        self.url = url
        self.prefetch_count = prefetch_count
        self.declare_passive = declare_passive
        self._connection: AbstractRobustConnection | None = None
        self._channel: AbstractRobustChannel | None = None
        self._queues: dict[str, AbstractQueue] = {}

    async def connect(self) -> None:
        if self._connection is not None and not self._connection.is_closed:
            return

        self._connection = await aio_pika.connect_robust(self.url)
        self._channel = await self._connection.channel()
        await self._channel.set_qos(prefetch_count=self.prefetch_count)
        logger.info(
            "래빗엠큐 연결 완료",
            extra={"prefetch_count": self.prefetch_count, "declare_passive": self.declare_passive},
        )

    async def close(self) -> None:
        if self._connection is not None and not self._connection.is_closed:
            await self._connection.close()
            logger.info("래빗엠큐 연결 종료")

    async def ensure_binding(self, binding: QueueBinding) -> None:
        channel = self._require_channel()
        exchange = await channel.declare_exchange(
            binding.exchange_name,
            ExchangeType.DIRECT,
            durable=True,
            passive=self.declare_passive,
        )
        queue = await channel.declare_queue(
            binding.queue_name,
            durable=True,
            passive=self.declare_passive,
        )
        await queue.bind(exchange, routing_key=binding.routing_key)
        self._queues[binding.queue_name] = queue
        logger.info(
            "래빗엠큐 바인딩 준비 완료",
            extra={
                "exchange": binding.exchange_name,
                "queue": binding.queue_name,
                "routing_key": binding.routing_key,
                "passive": self.declare_passive,
            },
        )

    async def consume(self, queue_name: str, handler: MessageHandler) -> str:
        queue = await self._get_or_declare_queue(queue_name)
        consumer_tag = await queue.consume(handler, no_ack=False)
        logger.info("래빗엠큐 컨슈머 시작", extra={"queue": queue_name, "consumer_tag": consumer_tag})
        return consumer_tag

    async def cancel_consumer(self, queue_name: str, consumer_tag: str) -> None:
        queue = self._queues.get(queue_name)
        if queue is None:
            queue = await self._get_or_declare_queue(queue_name)
        await queue.cancel(consumer_tag)
        logger.info("래빗엠큐 컨슈머 중지", extra={"queue": queue_name, "consumer_tag": consumer_tag})

    async def publish_json(
        self,
        *,
        exchange_name: str,
        routing_key: str,
        payload: dict[str, Any],
        message_id: str | None = None,
        correlation_id: str | None = None,
        message_type: str | None = None,
        headers: dict[str, Any] | None = None,
    ) -> None:
        channel = self._require_channel()
        exchange = await channel.declare_exchange(
            exchange_name,
            ExchangeType.DIRECT,
            durable=True,
            passive=self.declare_passive,
        )
        body = encode_json_message(payload)
        message = Message(
            body=body,
            content_type="application/json",
            content_encoding="utf-8",
            delivery_mode=DeliveryMode.PERSISTENT,
            message_id=message_id,
            correlation_id=correlation_id,
            type=message_type,
            headers=headers,
        )
        await exchange.publish(message, routing_key=routing_key)
        logger.info(
            "래빗엠큐 메시지 발행 완료",
            extra={
                "exchange": exchange_name,
                "routing_key": routing_key,
                "payload_size": len(json.dumps(payload, ensure_ascii=False)),
            },
        )

    def _require_channel(self) -> AbstractRobustChannel:
        if self._channel is None:
            raise RuntimeError("RabbitMQ channel is not initialized. Call connect() first.")
        return self._channel

    async def _get_or_declare_queue(self, queue_name: str) -> AbstractQueue:
        queue = self._queues.get(queue_name)
        if queue is not None:
            return queue
        channel = self._require_channel()
        queue = await channel.declare_queue(
            queue_name,
            durable=True,
            passive=self.declare_passive,
        )
        self._queues[queue_name] = queue
        return queue
