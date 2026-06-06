from fastapi import APIRouter

from storage.database import check_connection

router = APIRouter(tags=["health"])


@router.get("/health")
async def health_check() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/health/db")
async def database_health_check() -> dict[str, str | bool]:
    db_ok = await check_connection()
    return {"database": "connected" if db_ok else "disconnected", "healthy": db_ok}


@router.get("/health/ready")
async def readiness_check() -> dict[str, bool | str]:
    db_ok = await check_connection()
    return {
        "database": db_ok,
        "embeddings": True,  # If this endpoint is reachable, model is loaded
        "model": "BAAI/bge-small-en-v1.5",
    }
