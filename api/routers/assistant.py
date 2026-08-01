"""HazardGraph — AI assistant chat endpoint (Groq LLM)."""

import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from auth.jwt_service import get_current_user
from config.settings import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/assistant", tags=["assistant"])

SYSTEM_PROMPT = (
    "You are the HazardGraph AI assistant for the IGAD early-warning platform "
    "by Quantifaya. Help officers, coordinators, and data scientists understand "
    "hazard risk, climate regimes, causal drivers, forecasts, and recommended "
    "alert actions across the Horn of Africa. Provide plain definitions with "
    "IGAD meteorological context, and interpret provided data context "
    "(node/region/model/forecast) for decision-makers. Be concise and accurate."
)


class ChatRequest(BaseModel):
    message: str
    context: str | None = None


@router.post("/chat")
async def chat(req: ChatRequest, user=Depends(get_current_user)):
    """Send a message to the Groq LLM assistant with optional data context."""
    from groq import AsyncGroq

    if not settings.groq_api_key:
        raise HTTPException(status_code=503, detail="Groq API key not configured")

    client = AsyncGroq(api_key=settings.groq_api_key)

    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    if req.context:
        messages.append({"role": "system", "content": f"Context:\n{req.context}"})
    messages.append({"role": "user", "content": req.message})

    try:
        completion = await client.chat.completions.create(
            model=settings.groq_model,
            messages=messages,
            temperature=0.4,
            max_tokens=600,
        )
        reply = completion.choices[0].message.content or ""
        return {"reply": reply}
    except Exception as exc:
        logger.error("Groq chat failed: %s", exc)
        raise HTTPException(status_code=502, detail=f"Assistant request failed: {exc}")