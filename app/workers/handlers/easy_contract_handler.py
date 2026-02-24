from __future__ import annotations

import logging
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx
from aio_pika.abc import AbstractIncomingMessage

from app.resources.rabbitmq.codec import decode_json_message, parse_easy_contract_request
from app.resources.rabbitmq.result_publisher import RabbitMQResultPublisher
from app.services.cancel_registry import CancelRegistry
from app.services.easy_contract_service import EasyContractCancelled, EasyContractService

logger = logging.getLogger(__name__)


class EasyContractMessageHandler:
    def __init__(
        self,
        *,
        http: httpx.AsyncClient,
        easy_contract_service: EasyContractService,
        result_publisher: RabbitMQResultPublisher,
        cancel_registry: CancelRegistry,
    ) -> None:
        self.http = http
        self.easy_contract_service = easy_contract_service
        self.result_publisher = result_publisher
        self.cancel_registry = cancel_registry

    async def handle(self, message: AbstractIncomingMessage) -> None:
        job_id = self._fallback_job_id(message)
        result_status = "FAILED"
        result_data: dict[str, Any] | None = None
        result_error: dict[str, str] | None = {"code": "FAILED", "message": "쉬운 계약서 생성 중 오류가 발생했습니다."}

        try:
            payload = decode_json_message(message.body)
            request = parse_easy_contract_request(payload)
            job_id = self._extract_job_id(request, message)
            case_id = self._extract_case_id(request)
            docs = await self._extract_docs(request)

            markdown = await self.easy_contract_service.generate(
                case_id=case_id,
                docs=docs,
                job_id=job_id,
                is_cancelled=self.cancel_registry.is_cancelled,
            )
            result_status = "SUCCESS"
            result_data = {"markdown": markdown}
            result_error = None

        except EasyContractCancelled:
            result_status = "CANCELLED"
            result_data = None
            result_error = {"code": "CANCELLED", "message": "쉬운 계약서 생성이 취소되었습니다."}
        except ValueError as exc:
            result_status = "FAILED"
            result_data = None
            result_error = {"code": "INVALID_INPUT", "message": str(exc)}
        except Exception:
            logger.exception("쉬운 계약서 메시지 처리 실패")

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
                result_type="contract",
                status=status,
                data=data,
                error=error,
                correlation_id=message.correlation_id or job_id,
                message_id=message.message_id,
            )
            return True
        except Exception:
            logger.exception("쉬운 계약서 결과 발행 실패", extra={"job_id": job_id, "status": status})
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

    def _extract_case_id(self, request: dict[str, Any]) -> int:
        raw = request.get("case_id", request.get("id", -1))
        try:
            return int(raw)
        except (TypeError, ValueError):
            return -1

    async def _extract_docs(self, request: dict[str, Any]) -> list[dict[str, Any]]:
        files = request.get("files")
        normalized_files: list[dict[str, Any]] = []

        if isinstance(files, list) and files:
            for item in files:
                if not isinstance(item, dict):
                    raise ValueError("files는 객체 배열이어야 합니다.")
                normalized_files.append(item)
        else:
            single_url = request.get("file_url") or request.get("url")
            single_doc_type = request.get("file_type") or request.get("doc_type")
            if single_url and single_doc_type:
                normalized_files.append({"url": single_url, "doc_type": single_doc_type})

        if not normalized_files:
            raise ValueError("files 또는 file_url/doc_type 값이 필요합니다.")

        docs: list[dict[str, Any]] = []
        for idx, file_meta in enumerate(normalized_files, start=1):
            url = str(file_meta.get("url") or file_meta.get("file_url") or "").strip()
            if not url:
                raise ValueError("파일 URL이 누락되었습니다.")
            doc_type = str(file_meta.get("doc_type") or file_meta.get("file_type") or "").strip()
            if not doc_type:
                raise ValueError("doc_type(file_type)이 누락되었습니다.")

            filename = str(file_meta.get("filename") or self._filename_from_url(url) or f"file_{idx}").strip()
            file_bytes = await self._download(url)
            if not file_bytes:
                raise ValueError("비어있는 파일은 처리할 수 없습니다.")
            docs.append({"filename": filename, "bytes": file_bytes, "doc_type": doc_type})

        return docs

    async def _download(self, url: str) -> bytes:
        try:
            res = await self.http.get(url)
            res.raise_for_status()
            return res.content
        except httpx.HTTPError as exc:
            raise ValueError("파일 다운로드에 실패했습니다.") from exc

    def _filename_from_url(self, url: str) -> str:
        return Path(urlparse(url).path).name
