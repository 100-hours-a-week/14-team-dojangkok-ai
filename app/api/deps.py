from secrets import compare_digest

from fastapi import Header, HTTPException, Request

from app.bootstrap import AppContainer
from app.settings import settings


def get_container(request: Request) -> AppContainer:
    return request.app.state.container


def verify_backend_token(authorization: str | None = Header(default=None)) -> None:
    expected_token = settings.BACKEND_INTERNAL_TOKEN.strip()
    if not expected_token:
        raise HTTPException(
            status_code=500,
            detail={
                "error": {
                    "code": "SERVER_MISCONFIGURED",
                    "message": "서버 내부 인증키가 설정되지 않았습니다.",
                }
            },
        )

    expected_header = f"Bearer {expected_token}"
    received_header = (authorization or "").strip()
    if not received_header or not compare_digest(received_header, expected_header):
        raise HTTPException(
            status_code=401,
            detail={
                "error": {
                    "code": "UNAUTHORIZED",
                    "message": "유효하지 않은 인증키입니다.",
                }
            },
        )
