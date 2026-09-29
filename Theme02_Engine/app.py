"""FastAPI REST Service for Theme 2: Smart Guided Troubleshooting Engine.

Endpoints:
- GET  /health           -> Mandatory Gate G2 check ({"status": "ok"})
- POST /v1/troubleshoot  -> Translates query + siis_response into ContextDeeplinkResponse
"""

import logging
import os
from typing import Any, Dict
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field, field_validator

from engine import TroubleshootingEngine

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("theme2.engine")

app = FastAPI(
    title="Samsung Galaxy Smart Guided Troubleshooting Engine",
    description="Transforms device complaints and SIIS knowledge into deeplink-enriched troubleshooting guides.",
    version="1.0.0"
)

engine = TroubleshootingEngine()

DEBUG_MODE = os.getenv("THEME2_DEBUG", "false").lower() in ("true", "1", "yes")
DEBUG_SECRET = os.getenv("THEME2_DEBUG_SECRET", "")


class SiisPayload(BaseModel):
    model_config = {"extra": "ignore"}
    title: str = Field(default="", max_length=500)
    content: str = Field(default="", max_length=15000)


class TroubleshootRequest(BaseModel):
    model_config = {"extra": "ignore"}
    query: str = Field(..., min_length=1, max_length=1000)
    siis_response: SiisPayload = Field(default_factory=SiisPayload)

    @field_validator("query")
    @classmethod
    def validate_query(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Query cannot be empty or whitespace only.")
        return v.strip()


@app.get("/health")
async def health_check():
    """Gate G2 endpoint: Must return {'status': 'ok'}."""
    return {"status": "ok"}


@app.post("/v1/troubleshoot")
@app.post("/troubleshoot")
async def troubleshoot(req: TroubleshootRequest):
    """Main troubleshooting API: Returns schema-valid ContextDeeplinkResponse."""
    try:
        siis_dict = req.siis_response.model_dump()
        result = engine.troubleshoot(req.query, siis_dict)
        return result
    except Exception as e:
        logger.error("Internal processing error in troubleshoot: %s", e, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="An internal processing error occurred while generating troubleshooting guidance."
        )


if DEBUG_MODE:
    @app.post("/dev/troubleshoot/debug")
    async def troubleshoot_debug(req: TroubleshootRequest):
        """Development-only debug endpoint: returns diagnostic trace + official response."""
        try:
            siis_dict = req.siis_response.model_dump()
            return engine.troubleshoot_debug(req.query, siis_dict)
        except Exception as e:
            logger.error("Internal debug processing error: %s", e, exc_info=True)
            raise HTTPException(
                status_code=500,
                detail="An internal processing error occurred while generating debug trace."
            )

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
    host = os.getenv("HOST", "127.0.0.1")
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run(app, host=host, port=port)
