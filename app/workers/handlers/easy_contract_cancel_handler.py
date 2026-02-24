from __future__ import annotations

import logging

from aio_pika.abc import AbstractIncomingMessage

from app.resources.rabbitmq.codec import decode_json_message, parse_easy_contract_cancel
from app.services.cancel_registry import CancelRegistry

logger = logging.getLogger(__name__)


class EasyContractCancelMessageHandler:
    def __init__(self, *, cancel_registry: CancelRegistry) -> None:
        self.cancel_registry = cancel_registry

    async def handle(self, message: AbstractIncomingMessage) -> None:
        try:
            payload = decode_json_message(message.body)
            request = parse_easy_contract_cancel(payload)
            job_id = str(request.get("job_id") or "").strip()
            if job_id:
                self.cancel_registry.mark_cancelled(job_id)
                logger.info("쉬운 계약서 취소 요청 수신", extra={"job_id": job_id})
            else:
                logger.warning("job_id가 없는 취소 메시지 수신")
        except Exception:
            logger.exception("쉬운 계약서 취소 메시지 처리 실패")
        finally:
            if not message.processed:
                await message.ack()
