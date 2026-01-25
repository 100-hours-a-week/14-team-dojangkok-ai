from pydantic import BaseModel

class EasyContractAcceptedResponse(BaseModel):
    id: int
    message: str
