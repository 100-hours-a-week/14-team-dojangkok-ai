from typing import Any
import logging

import httpx

logger = logging.getLogger(__name__)


class VLLMClient:
    def __init__(
        self,
        http: httpx.AsyncClient,
        base_url: str,
        api_key: str,
        model: str,
    ):
        self.http = http
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model

    async def chat(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.2,
        max_tokens: int = 1024,
        model: str | None = None,
    ) -> str:
        url = f"{self.base_url}/chat/completions"
        headers = {"Authorization": f"Bearer {self.api_key}"}
        requested_model = self._resolve_model(model)

        payload: dict[str, Any] = {
            "model": requested_model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        try:
            res = await self.http.post(url, json=payload, headers=headers)
            res.raise_for_status()
        except httpx.HTTPStatusError as exc:
            if not self._should_retry_with_base_model(exc, requested_model):
                raise
            logger.warning(
                "LoRA adapter model request failed; retrying with base model",
                extra={"requested_model": requested_model, "base_model": self.model},
            )
            payload["model"] = self.model
            res = await self.http.post(url, json=payload, headers=headers)
            res.raise_for_status()

        data = res.json()
        return data["choices"][0]["message"]["content"]

    def _resolve_model(self, model: str | None) -> str:
        if model is None:
            return self.model
        candidate = model.strip()
        if candidate.lower() in {"", "none", "null"}:
            return self.model
        return candidate

    def _should_retry_with_base_model(self, exc: httpx.HTTPStatusError, requested_model: str) -> bool:
        if requested_model == self.model:
            return False

        response = exc.response
        if response is None:
            return False
        if response.status_code not in {400, 404, 422}:
            return False

        try:
            body = response.json()
        except Exception:
            body = response.text

        text = str(body).lower()
        missing_model_hints = ("not found", "does not exist", "unknown", "lora", "adapter")
        return "model" in text and any(hint in text for hint in missing_model_hints)
