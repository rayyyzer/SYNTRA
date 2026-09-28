"""FastAPI REST Service for Theme 2: Smart Guided Troubleshooting Engine.

Endpoints:
- GET  /health           -> Mandatory Gate G2 check ({"status": "ok"})
- POST /v1/troubleshoot  -> Translates query + siis_response into ContextDeeplinkResponse
"""

from __future__ import annotations
from typing import Any, Dict
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from engine import TroubleshootingEngine

app = FastAPI(
    title="Samsung Galaxy Smart Guided Troubleshooting Engine",
    description="Transforms device complaints and SIIS knowledge into deeplink-enriched troubleshooting guides.",
    version="1.0.0"
)

engine = TroubleshootingEngine()


class TroubleshootRequest(BaseModel):
    query: str
    siis_response: Dict[str, Any]


@app.get("/health")
async def health_check():
    """Gate G2 endpoint: Must return {'status': 'ok'}."""
    return {"status": "ok"}


@app.post("/v1/troubleshoot")
async def troubleshoot(req: TroubleshootRequest):
    """Main troubleshooting API: Returns schema-valid ContextDeeplinkResponse."""
    try:
        result = engine.troubleshoot(req.query, req.siis_response)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
