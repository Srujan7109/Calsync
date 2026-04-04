from __future__ import annotations

import uuid
from importlib import import_module

from app.agent.prompts import SYSTEM_PROMPT
from app.agent.tools import CalsyncTools
from app.config import get_settings
from app.models.agent_models import AgentProcessResponse, AgentResult
from app.models.email_models import AgentProcessPayload


def _looks_like_new_meeting(subject: str, body_text: str) -> bool:
    text = f"{subject} {body_text}".lower()
    return any(word in text for word in ["meeting", "schedule", "available", "sync", "call"])


async def _optional_llm_trace(payload: AgentProcessPayload, tool_status: str) -> str:
    settings = get_settings()
    if not settings.langchain_enabled:
        return (
            "Thought: Analyze inbound email for scheduling intent. "
            f"Action: tool_pipeline({tool_status}). Observation: queued state update and follow-up."
        )

    if not settings.openai_api_key:
        return (
            "Thought: LLM disabled due to missing OPENAI_API_KEY. "
            f"Action: deterministic pipeline({tool_status})."
        )

    try:
        prompts_module = import_module("langchain_core.prompts")
        output_module = import_module("langchain_core.output_parsers")
        openai_module = import_module("langchain_openai")
    except ModuleNotFoundError:
        return (
            "Thought: LangChain packages unavailable. "
            f"Action: deterministic pipeline({tool_status})."
        )

    prompt = prompts_module.ChatPromptTemplate.from_messages(
        [
            ("system", SYSTEM_PROMPT),
            (
                "human",
                "Generate a one-line ReAct-style trace for this email. "
                "Subject: {subject}. Body: {body}. Tool status: {tool_status}.",
            ),
        ]
    )
    llm = openai_module.ChatOpenAI(model=settings.openai_model, api_key=settings.openai_api_key, temperature=0)
    chain = prompt | llm | output_module.StrOutputParser()
    return await chain.ainvoke(
        {
            "subject": payload.subject,
            "body": payload.body_text[:500],
            "tool_status": tool_status,
        }
    )


async def run_react_agent(payload: AgentProcessPayload) -> AgentProcessResponse:
    tools = CalsyncTools()

    session_outcome = await tools.create_session(
        thread_id=payload.thread_id or f"thread_{payload.message_id}",
        organizer=payload.from_email,
        participants=payload.participants,
    )
    parse_outcome = await tools.parse_availability(payload.body_text)

    if _looks_like_new_meeting(payload.subject, payload.body_text):
        action = "SENT_AVAILABILITY_REQUEST"
    else:
        action = "NO_ACTION"

    tool_status = f"create_session={session_outcome.status}, parse_availability={parse_outcome.status}"
    reasoning_trace = await _optional_llm_trace(payload, tool_status)

    session_id = str(session_outcome.payload.get("session_id") or f"sess_{uuid.uuid4().hex[:8]}")

    return AgentProcessResponse(
        agent_result=AgentResult(
            action_taken=action,
            session_id=session_id,
            emails_sent_to=payload.participants,
            reasoning_trace=reasoning_trace,
        )
    )
