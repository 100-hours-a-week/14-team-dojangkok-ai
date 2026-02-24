from __future__ import annotations

import logging
from typing import Any

from aio_pika.abc import AbstractIncomingMessage

from app.resources.rabbitmq.codec import decode_json_message, parse_checklist_request
from app.resources.rabbitmq.result_publisher import RabbitMQResultPublisher
from app.services.checklist_service import ChecklistService

logger = logging.getLogger(__name__)


class ChecklistMessageHandler:
    def __init__(
        self,
        *,
        checklist_service: ChecklistService,
        result_publisher: RabbitMQResultPublisher,
    ) -> None:
        self.checklist_service = checklist_service
        self.result_publisher = result_publisher

    async def handle(self, message: AbstractIncomingMessage) -> None:
        job_id = self._fallback_job_id(message)
        result_status = "FAILED"
        result_data: dict[str, Any] | None = None
        result_error: dict[str, str] | None = {"code": "FAILED", "message": "체크리스트 생성 중 오류가 발생했습니다."}

        try:
            payload = decode_json_message(message.body)
            request = parse_checklist_request(payload)
            job_id = self._extract_job_id(request, message)
            keywords = self._extract_keywords(request)

            checklists = await self.checklist_service.generate(case_id=job_id, keywords=keywords)
            result_status = "SUCCESS"
            result_data = {"checklists": checklists}
            result_error = None

        except ValueError as exc:
            result_status = "FAILED"
            result_data = None
            result_error = {"code": "INVALID_INPUT", "message": str(exc)}
        except Exception:
            logger.exception("체크리스트 메시지 처리 실패")

        publish_ok = await self._publish_result(
            job_id=job_id,
            status=result_status,
            data=result_data,
            error=result_error,
            message=message,
        )
        if publish_ok and not message.processed:
            await message.ack()
        elif not publish_ok and not message.processed:
            await message.nack(requeue=True)

    async def _publish_result(
        self,
        *,
        job_id: str,
        status: str,
        data: dict[str, Any] | None,
        error: dict[str, str] | None,
        message: AbstractIncomingMessage,
    ) -> bool:
        try:
            await self.result_publisher.publish_result(
                job_id=job_id,
                result_type="checklist",
                status=status,
                data=data,
                error=error,
                correlation_id=message.correlation_id or job_id,
                message_id=message.message_id,
            )
            return True
        except Exception:
            logger.exception("체크리스트 결과 발행 실패", extra={"job_id": job_id, "status": status})
            return False

    def _extract_job_id(self, request: dict[str, Any], message: AbstractIncomingMessage) -> str:
        raw = request.get("job_id")
        if raw is None:
            return self._fallback_job_id(message)
        job_id = str(raw).strip()
        if not job_id:
            return self._fallback_job_id(message)
        return job_id

    def _fallback_job_id(self, message: AbstractIncomingMessage) -> str:
        return str(message.correlation_id or message.message_id or "unknown")

    def _extract_keywords(self, request: dict[str, Any]) -> list[str]:
        keywords = request.get("keywords")
        if keywords is None:
            return []
        if not isinstance(keywords, list) or any(not isinstance(x, str) for x in keywords):
            raise ValueError("keywords는 문자열 배열이어야 합니다.")
        return keywords
