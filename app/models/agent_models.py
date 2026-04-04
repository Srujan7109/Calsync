from pydantic import BaseModel, Field


class AgentResult(BaseModel):
    action_taken: str = Field(description="Final action selected by the agent")
    session_id: str = Field(description="Session id for state tracking")
    emails_sent_to: list[str] = Field(default_factory=list, description="Recipients notified by the workflow")
    reasoning_trace: str = Field(description="High-level thought/action trace for observability")


class AgentProcessResponse(BaseModel):
    agent_result: AgentResult
