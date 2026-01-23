from pydantic import BaseModel, Field
from typing import List, Optional

class ChecklistRequest(BaseModel):
    keywords: Optional[List[str]] = Field(default=None, description="라이프스타일 키워드 목록(자연어 가능)")

class ChecklistAcceptedResponse(BaseModel):
    id: str
    message: str
