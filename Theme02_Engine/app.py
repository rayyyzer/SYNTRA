"""FastAPI REST Service for Theme 2: Smart Guided Troubleshooting Engine.

Endpoints:
- GET  /health           -> Mandatory Gate G2 check ({"status": "ok"})
- POST /v1/troubleshoot  -> Translates query + siis_response into ContextDeeplinkResponse
"""

from __future__ import annotations
import os
from typing import Any, Dict
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from engine import TroubleshootingEngine

app = FastAPI(
    title="Samsung Galaxy Smart Guided Troubleshooting Engine",
    description="Transforms device complaints and SIIS knowledge into deeplink-enriched troubleshooting guides.",
    version="1.0.0"
)

engine = TroubleshootingEngine()

DEBUG_MODE = os.getenv("THEME2_DEBUG", "false").lower() in ("true", "1", "yes")


class TroubleshootRequest(BaseModel):
    query: str
    siis_response: Dict[str, Any]


@app.get("/health")
async def health_check():
    """Gate G2 endpoint: Must return {'status': 'ok'}."""
    return {"status": "ok"}


@app.post("/v1/troubleshoot")
@app.post("/troubleshoot")
async def troubleshoot(req: TroubleshootRequest):
    """Main troubleshooting API: Returns schema-valid ContextDeeplinkResponse."""
    try:
        result = engine.troubleshoot(req.query, req.siis_response)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


if DEBUG_MODE:
    @app.post("/dev/troubleshoot/debug")
    async def troubleshoot_debug(req: TroubleshootRequest):
        """Development-only debug endpoint: returns diagnostic trace + official response."""
        try:
            return engine.troubleshoot_debug(req.query, req.siis_response)
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @app.get("/dev/playground", response_class=HTMLResponse)
    async def serve_playground():
        """Development Test Playground Browser UI."""
        playground_path = os.path.join(os.path.dirname(__file__), "playground.html")
        if os.path.exists(playground_path):
            with open(playground_path, "r", encoding="utf-8") as f:
                return HTMLResponse(content=f.read())
        return HTMLResponse(content="<h1>Playground UI file not found</h1>", status_code=404)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
