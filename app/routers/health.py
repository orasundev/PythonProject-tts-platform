"""
Health check (/health) and Prometheus metrics (/metrics) endpoints.
"""

from fastapi import APIRouter
from sqlalchemy import text

router = APIRouter(tags=["observability"])


@router.get("/health")
async def health_check():
    from app.database import AsyncSessionLocal
    from app.services.usage_service import get_redis
    from app.utils.s3 import check_bucket_accessible

    checks: dict[str, str] = {}

    # Database
    try:
        async with AsyncSessionLocal() as session:
            await session.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception as exc:
        checks["database"] = f"fail: {exc}"

    # Redis
    try:
        r = get_redis()
        await r.ping()
        checks["redis"] = "ok"
    except Exception as exc:
        checks["redis"] = f"fail: {exc}"

    # S3
    try:
        ok = check_bucket_accessible()
        checks["s3"] = "ok" if ok else "fail: bucket not reachable"
    except Exception as exc:
        checks["s3"] = f"fail: {exc}"

    # Celery
    try:
        from app.tasks import celery_app
        inspect = celery_app.control.inspect(timeout=2)
        ping = inspect.ping()
        checks["celery"] = "ok" if ping else "fail: no workers responded"
    except Exception as exc:
        checks["celery"] = f"fail: {exc}"

    all_ok = all(v == "ok" for v in checks.values())
    return {"status": "healthy" if all_ok else "degraded", **checks}
