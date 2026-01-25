from dataclasses import dataclass

import httpx

from app.resources.http.client import create_async_http_client
from app.resources.vllm.client import VLLMClient
from app.services.callback_service import CallbackService
from app.services.checklist_service import ChecklistService
from app.settings import settings


@dataclass
class AppContainer:
    http: httpx.AsyncClient
    vllm: VLLMClient
    callback: CallbackService
    checklist_service: ChecklistService

    async def aclose(self) -> None:
        await self.http.aclose()


async def create_container() -> AppContainer:
    http = create_async_http_client(timeout_sec=settings.HTTP_TIMEOUT_SEC)

    vllm = VLLMClient(
        http=http,
        base_url=settings.VLLM_BASE_URL,
        api_key=settings.VLLM_API_KEY,
        model=settings.VLLM_MODEL,
        lora_adapter=settings.VLLM_LORA_ADAPTER,
    )

    callback = CallbackService(
        http=http,
        base_url=settings.BACKEND_CALLBACK_BASE_URL,
        token=settings.BACKEND_INTERNAL_TOKEN,
    )

    checklist_service = ChecklistService(vllm=vllm)

    return AppContainer(
        http=http,
        vllm=vllm,
        callback=callback,
        checklist_service=checklist_service,
    )
