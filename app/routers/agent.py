from __future__ import annotations

from fastapi import APIRouter

from app.agent.react_agent import run_react_agent
from app.models.agent_models import AgentProcessResponse
from app.models.email_models import AgentProcessPayload


router = APIRouter(prefix="/api/v1/agent", tags=["agent"])


@router.post(
    "/process",
    response_model=AgentProcessResponse,
    summary="Process an email through the coordination agent",
    description="Internal trigger endpoint for Gemini + MCP orchestration.",
    responses={
        200: {
            "description": "Agent execution completed",
            "content": {
                "application/json": {
                    "example": {
                        "agent_result": {
                            "action_taken": "SENT_AVAILABILITY_REQUEST",
                            "session_id": "sess_xyz789",
                            "emails_sent_to": ["bob@example.com"],
                            "reasoning_trace": "Thought: New meeting request. Action: create_session. Observation: waiting for replies.",
                        }
                    }
                }
            },
        }
    },
)
async def process_email(payload: AgentProcessPayload) -> AgentProcessResponse:
    return await run_react_agent(payload)
