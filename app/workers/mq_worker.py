from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable

from aio_pika.abc import AbstractIncomingMessage

from app.resources.rabbitmq.client import RabbitMQClient

logger = logging.getLogger(__name__)

MessageHandler = Callable[[AbstractIncomingMessage], Awaitable[None]]


class RabbitMQWorker:
    def __init__(
        self,
        *,
        client: RabbitMQClient,
        easy_contract_queue: str,
        checklist_queue: str,
        easy_contract_cancel_queue: str,
        easy_contract_handler: MessageHandler,
        checklist_handler: MessageHandler,
        easy_contract_cancel_handler: MessageHandler,
    ) -> None:
        self.client = client
        self.easy_contract_queue = easy_contract_queue
        self.checklist_queue = checklist_queue
        self.easy_contract_cancel_queue = easy_contract_cancel_queue
        self.easy_contract_handler = easy_contract_handler
        self.checklist_handler = checklist_handler
        self.easy_contract_cancel_handler = easy_contract_cancel_handler
        self._consumer_tags: dict[str, str] = {}
        self._started = False

    async def start(self) -> None:
        if self._started:
            return

        self._consumer_tags[self.easy_contract_queue] = await self.client.consume(
            self.easy_contract_queue,
            self._wrap_handler(self.easy_contract_handler, queue_name=self.easy_contract_queue),
        )
        self._consumer_tags[self.checklist_queue] = await self.client.consume(
            self.checklist_queue,
            self._wrap_handler(self.checklist_handler, queue_name=self.checklist_queue),
        )
        self._consumer_tags[self.easy_contract_cancel_queue] = await self.client.consume(
            self.easy_contract_cancel_queue,
            self._wrap_handler(self.easy_contract_cancel_handler, queue_name=self.easy_contract_cancel_queue),
        )
        self._started = True
        logger.info("래빗엠큐 워커 시작")

    async def stop(self) -> None:
        if not self._started:
            return
        for queue_name, consumer_tag in list(self._consumer_tags.items()):
            try:
                await self.client.cancel_consumer(queue_name, consumer_tag)
            except Exception:
                logger.exception(
                    "래빗엠큐 컨슈머 중지 실패",
                    extra={"queue": queue_name, "consumer_tag": consumer_tag},
                )
        self._consumer_tags.clear()
        self._started = False
        logger.info("래빗엠큐 워커 종료")

    def _wrap_handler(self, handler: MessageHandler, *, queue_name: str) -> MessageHandler:
        async def wrapped(message: AbstractIncomingMessage) -> None:
            try:
                await handler(message)
            except Exception:
                logger.exception("메시지 핸들러 처리 중 예외 발생", extra={"queue": queue_name})
                if not message.processed:
                    try:
                        await message.nack(requeue=True)
                    except Exception:
                        logger.exception("메시지 nack 처리 실패", extra={"queue": queue_name})

        return wrapped
