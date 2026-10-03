"""HTTP entry point for Omar Core.

Run with: uvicorn omar_core.app:app --host 0.0.0.0 --port 8080
"""
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from .router import OmarRouter, RouteError

app = FastAPI(title="Omar Core", version="1.0.0")
router = OmarRouter()


class RouteRequest(BaseModel):
    business_id: str = Field(min_length=1)
    visual: bool = False


@app.get("/health")
def health() -> dict:
    return {"ok": True, "service": "omar-core", "registry_version": router.registry.get("schema_version")}


@app.post("/omar/route")
def route(req: RouteRequest) -> dict:
    try:
        plan = router.route(req.business_id, visual=req.visual)
    except RouteError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, "route": plan.as_dict()}
