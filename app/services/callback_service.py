from typing import Any

import httpx


class CallbackService:
    def __init__(self, http: httpx.AsyncClient, base_url: str, token: str):
        self.http = http
        self.base_url = base_url.rstrip("/")
        self.token = token

    async def post_checklist_complete(self, case_id: str, payload: dict[str, Any]) -> None:
        print("체크리스트 콜백 시작")
        url = f"{self.base_url}/internal/callbacks/checklists/{case_id}/complete"
        headers = {"Content-Type": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        print(payload)

        res = await self.http.post(url, json=payload, headers=headers)
        res.raise_for_status()
        print("체크리스트 콜백 성공")
