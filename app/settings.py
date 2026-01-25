import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    APP_ENV: str = os.getenv("APP_ENV", "dev")

    VLLM_BASE_URL: str = os.getenv("VLLM_BASE_URL", "")
    VLLM_API_KEY: str = os.getenv("VLLM_API_KEY", "")
    VLLM_MODEL: str = os.getenv("VLLM_MODEL", "LGAI-EXAONE/EXAONE-3.5-2.4B-Instruct")

    VLLM_LORA_ADAPTER: str = os.getenv("VLLM_LORA_ADAPTER", "")

    BACKEND_CALLBACK_BASE_URL: str = os.getenv("BACKEND_CALLBACK_BASE_URL", "")
    BACKEND_INTERNAL_TOKEN: str = os.getenv("BACKEND_INTERNAL_TOKEN", "")

    HTTP_TIMEOUT_SEC: float = float(os.getenv("HTTP_TIMEOUT_SEC", "300.0"))


settings = Settings()
