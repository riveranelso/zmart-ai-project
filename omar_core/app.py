"""HTTP entry point for Omar Core.

Run with: uvicorn omar_core.app:app --host 0.0.0.0 --port 8080
"""
from fastapi import Depends, FastAPI, HTTPException, Request
from pydantic import BaseModel, Field

from .router import OmarRouter, RouteError
from .security import enforce_rate_limit, require_api_key

app = FastAPI(
    title="Omar Core",
    version="1.1.0",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)
router = OmarRouter()


class RouteRequest(BaseModel):
    business_id: str = Field(
        min_length=1,
        max_length=64,
        pattern=r"^[a-z0-9][a-z0-9-]*$",
    )
    visual: bool = False


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Cache-Control"] = "no-store"
    return response


@app.get("/health")
def health() -> dict:
    # Keep public health output intentionally minimal.
    return {"ok": True, "service": "omar-core"}


@app.post(
    "/omar/route",
    dependencies=[Depends(require_api_key), Depends(enforce_rate_limit)],
)
def route(req: RouteRequest) -> dict:
    try:
        plan = router.route(req.business_id, visual=req.visual)
    except RouteError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, "route": plan.as_dict()}
