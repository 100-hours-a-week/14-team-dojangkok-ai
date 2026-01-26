from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.routers.checklist import router as checklist_router
from app.api.routers.easy_contract import router as easy_contract_router
from app.bootstrap import create_container


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.container = await create_container()
    yield
    await app.state.container.aclose()


app = FastAPI(
    title="DojangKok AI Server",
    description="AI service for DojangKok",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(checklist_router)
app.include_router(easy_contract_router)


@app.get("/health")
def health_check():
    return {"status": "ok"}
