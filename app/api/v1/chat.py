import logging

import base64

from typing import Dict, List, Optional



from fastapi import APIRouter, Depends

from pydantic import BaseModel, Field, field_validator



from app.services.ai_engine.chat import chat_assistant

from app.services.image_analysis.analyzer import chart_analyzer

from app.services.ai_engine.trade_plan import trade_plan_service

from app.services.data_ingestion.historical import DataUnavailable

from app.core.ratelimit import limit_chat

from app.core.config import settings



router = APIRouter()



logger = logging.getLogger(__name__)





_MAX_HISTORY_MESSAGES = 20
_MAX_HISTORY_CHARS = 4000


class ChatRequest(BaseModel):

    message: str = Field(..., min_length=1, max_length=2000)

    history: Optional[List[Dict[str, str]]] = None

    @field_validator("history")
    @classmethod
    def _bound_history(cls, v):
        if v is None:
            return v
        if len(v) > _MAX_HISTORY_MESSAGES:
            raise ValueError(f"history exceeds {_MAX_HISTORY_MESSAGES} messages")
        for m in v:
            if not isinstance(m, dict):
                raise ValueError("history entries must be objects")
            if len(m.get("content") or "") > _MAX_HISTORY_CHARS:
                raise ValueError("history message too long")
        return v





class ChatMessage(BaseModel):

    role: str  # "user" | "assistant"

    content: str





class ChatResponse(BaseModel):

    reply: str

    suggestions: List[str] = []

    context: Dict = {}





@router.post("", dependencies=[Depends(limit_chat)])

async def chat(req: ChatRequest) -> ChatResponse:

    """Chat with the Quant AI Terminal assistant.



    Data-aware: detects symbols, pulls live ticks (if the feed is connected),

    scores news with FinBERT, and reports risk settings. Fully graceful offline.

    """

    if not settings.CHAT_ENABLED:

        return ChatResponse(

            reply="Chat is disabled on this deployment.",

            suggestions=[],

            context={"disabled": True},

        )

    result = await chat_assistant.respond(req.message, req.history)

    return ChatResponse(

        reply=result["reply"],

        suggestions=result.get("suggestions", []),

        context=result.get("context", {}),

    )





@router.get("/suggestions")

async def chat_suggestions() -> Dict[str, List[str]]:

    return {"suggestions": chat_assistant.suggestions()}


class SnapshotRequest(BaseModel):
    image: str = Field(..., description="base64 PNG, optionally 'data:image/png;base64,...' prefixed")
    symbol: Optional[str] = None

    @field_validator("image")
    @classmethod
    def _validate_image(cls, v):
        if not v:
            raise ValueError("image is required")
        # strip optional data-URI prefix, then validate server-side (standard 2.1)
        payload = v.split(",", 1)[1] if "," in v else v
        try:
            raw = base64.b64decode(payload, validate=True)
        except Exception:
            raise ValueError("image must be valid base64")
        max_bytes = int(settings.MAX_UPLOAD_SIZE_MB * 1_000_000)
        if len(raw) > max_bytes:
            raise ValueError(
                f"image too large: {len(raw)} bytes > {max_bytes} bytes "
                f"(MAX_UPLOAD_SIZE_MB={settings.MAX_UPLOAD_SIZE_MB})"
            )
        return v

@router.post("/snapshot", dependencies=[Depends(limit_chat)])
async def snapshot(req: SnapshotRequest) -> ChatResponse:
    """Analyze a chart snapshot from the chat panel.

    Runs OCR/pattern analysis on the image and (when a symbol is known) builds a
    trade plan (entry/SL/TP/forecast/patterns) that the frontend draws on the
    chart. Returns a chat-ready reply describing the findings.
    """
    result = await chat_assistant.analyze_snapshot(req.image, req.symbol)
    return ChatResponse(
        reply=result["reply"],
        suggestions=chat_assistant.suggestions(),
        context={
            "intent": "snapshot",
            "symbol": result.get("symbol"),
            "has_plan": result.get("plan") is not None,
        },
    )

