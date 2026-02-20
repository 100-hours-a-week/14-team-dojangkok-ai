# v2: Docker + MIG rolling update 배포 방식 적용
# CI/CD pipeline trigger test
from dataclasses import dataclass

import httpx
from aiolimiter import AsyncLimiter

from app.resources.http.client import create_async_http_client
from app.resources.vllm.client import VLLMClient
from app.services.callback_service import CallbackService
from app.services.checklist_service import ChecklistService
from app.services.easy_contract_service import EasyContractService
from app.resources.ocr.upstage_client import UpstageDocumentParseClient
from app.settings import settings


@dataclass
class AppContainer:
    http: httpx.AsyncClient
    vllm: VLLMClient
    callback: CallbackService
    checklist_service: ChecklistService
    easy_contract_service: EasyContractService
    upstage: UpstageDocumentParseClient

    async def aclose(self) -> None:
        await self.http.aclose()


async def create_container() -> AppContainer:
    http = create_async_http_client(timeout_sec=settings.HTTP_TIMEOUT_SEC)

    vllm = VLLMClient(
        http=http,
        base_url=settings.VLLM_BASE_URL,
        api_key=settings.VLLM_API_KEY,
        model=settings.VLLM_MODEL,
    )

    ocr_limiter = AsyncLimiter(1, time_period=2)
    upstage = UpstageDocumentParseClient(
        http=http,
        api_key=settings.UPSTAGE_API_KEY,
        url=settings.UPSTAGE_DOCUMENT_PARSE_URL,
        limiter=ocr_limiter,
    )

    callback = CallbackService(
        http=http,
        base_url=settings.BACKEND_CALLBACK_BASE_URL,
        token=settings.BACKEND_INTERNAL_TOKEN,
    )

    checklist_service = ChecklistService(vllm=vllm)
    easy_contract_service = EasyContractService(vllm=vllm, ocr=upstage)


    return AppContainer(
        http=http,
        vllm=vllm,
        callback=callback,
        checklist_service=checklist_service,
        easy_contract_service=easy_contract_service,
        upstage=upstage,
    )
