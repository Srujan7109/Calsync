from pydantic import BaseModel, Field


class EmailWebhookPayload(BaseModel):
    sender: str = Field(default="", description="Sender email address", examples=["alice@example.com"])
    to: str = Field(default="", description="Recipient mailbox address", examples=["calsync@yourdomain.com"])
    subject: str = Field(default="", description="Email subject", examples=["Schedule a team sync"])
    text: str = Field(default="", description="Plain text email body")
    html: str | None = Field(default=None, description="HTML body if present")
    message_id: str = Field(default="", description="RFC message id", examples=["<CABc123@mail.gmail.com>"])
    headers: str | None = Field(default=None, description="Raw headers blob")
    spam_score: str | None = Field(default=None, description="Spam score from provider", examples=["0.1"])


class WebhookAcceptedResponse(BaseModel):
    status: str = Field(default="accepted", description="Webhook request accepted for async processing")
    task_id: str = Field(description="Generated background task id", examples=["bg_task_abc123"])


class DuplicateResponse(BaseModel):
    status: str = Field(default="duplicate_discarded", description="Duplicate email ignored by idempotency layer")


class NotSchedulingResponse(BaseModel):
    status: str = Field(default="not_scheduling_related", description="Email filtered out by scheduling keyword edge filter")


class AgentProcessPayload(BaseModel):
    email_hash: str = Field(description="SHA-256 hash for deduplication")
    message_id: str = Field(description="Original email message id")
    from_email: str = Field(description="Sender email")
    subject: str = Field(description="Email subject")
    body_text: str = Field(description="Email plain text body")
    thread_id: str = Field(default="", description="Conversation thread id if available")
    in_reply_to: str = Field(default="", description="RFC 2822 In-Reply-To header")
    references: str = Field(default="", description="RFC 2822 References header chain")
    participants: list[str] = Field(default_factory=list)
    received_at: str = Field(description="UTC timestamp when Calsync received the email")


class ImapPollResponse(BaseModel):
    status: str = Field(default="ok", description="Polling request status")
    fetched: int = Field(default=0, description="Count of emails fetched from IMAP")
    accepted: int = Field(default=0, description="Count of emails queued for background processing")
    duplicates: int = Field(default=0, description="Count of duplicates ignored")
    filtered_out: int = Field(default=0, description="Count of emails rejected by keyword filter")
