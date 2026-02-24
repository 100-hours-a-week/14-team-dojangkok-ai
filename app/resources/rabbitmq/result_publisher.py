from __future__ import annotations

from typing import Any

from app.resources.rabbitmq.client import RabbitMQClient
from app.resources.rabbitmq.codec import build_result_payload


class RabbitMQResultPublisher:
    def __init__(self, *, client: RabbitMQClient, exchange_name: str, routing_key: str) -> None:
        self.client = client
        self.exchange_name = exchange_name
        self.routing_key = routing_key

    async def publish(
        self,
        payload: dict[str, Any],
        *,
        message_id: str | None = None,
        correlation_id: str | None = None,
        message_type: str | None = None,
        headers: dict[str, Any] | None = None,
    ) -> None:
        await self.client.publish_json(
            exchange_name=self.exchange_name,
            routing_key=self.routing_key,
            payload=payload,
            message_id=message_id,
            correlation_id=correlation_id,
            message_type=message_type,
            headers=headers,
        )

    async def publish_result(
        self,
        *,
        job_id: str,
        result_type: str,
        status: str,
        data: dict[str, Any] | None = None,
        error: dict[str, Any] | None = None,
        message_id: str | None = None,
        correlation_id: str | None = None,
        headers: dict[str, Any] | None = None,
    ) -> None:
        payload = build_result_payload(
            job_id=job_id,
            result_type=result_type,
            status=status,
            data=data,
            error=error,
        )
        await self.publish(
            payload,
            message_id=message_id,
            correlation_id=correlation_id,
            message_type=result_type,
            headers=headers,
        )
