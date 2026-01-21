from fastapi import FastAPI

app = FastAPI(
    title="DojangKok AI Server",
    description="AI service for DojangKok",
    version="0.1.0",
)


@app.get("/health")
def health_check():
    """Health check endpoint for load balancer and CD verification."""
    return {"status": "ok"}
