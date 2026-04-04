from fastapi import APIRouter, Request
from pydantic import BaseModel, Field


router = APIRouter(prefix="/webhooks", tags=["webhooks"])


class WebhookAck(BaseModel):
    received: bool = Field(default=True)
    message: str = Field(default="Webhook received")


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.post("/events", response_model=WebhookAck)
async def receive_event(request: Request) -> WebhookAck:
    await request.body()
    return WebhookAck()
