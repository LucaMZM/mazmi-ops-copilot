from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ChatRequest(StrictModel):
    message: str = Field(min_length=1, max_length=8000)
    conversation_id: UUID | None = None
    mode: Literal["ASK", "DO"] = "ASK"


class TicketPayload(StrictModel):
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1, max_length=8000)
    priority: Literal["LOW", "MEDIUM", "HIGH", "URGENT"]


class Source(BaseModel):
    chunk_id: int
    document_id: str
    filename: str
    page: int | None
    excerpt: str
    score: float


class PendingAction(BaseModel):
    id: str
    name: Literal["create_ticket"]
    payload: TicketPayload


class ChatResponse(BaseModel):
    conversation_id: str
    answer: str
    sources: list[Source] = Field(default_factory=list)
    pending_action: PendingAction | None = None


class ActionDecision(StrictModel):
    approved: bool = Field(strict=True)


class VoiceRequest(StrictModel):
    text: str = Field(min_length=1, max_length=4000)
