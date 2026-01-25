import httpx

class UpstageDocumentParseClient:
    def __init__(self, http: httpx.AsyncClient, api_key: str, url: str):
        self.http = http
        self.api_key = api_key
        self.url = url

    async def parse_image(self, image_bytes: bytes, filename: str = "page.png") -> dict:
        headers = {"Authorization": f"Bearer {self.api_key}"}
        files = {"document": (filename, image_bytes, "image/png")}
        data = {"ocr": "force", "base64_encoding": "['table']", "model": "document-parse"}
        res = await self.http.post(self.url, headers=headers, files=files, data=data)
        res.raise_for_status()
        return res.json()