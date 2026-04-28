from datetime import datetime

from pydantic import BaseModel


class TokenUsage(BaseModel):
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_creation_tokens: int = 0


class ParsedMessage(BaseModel):
    sequence: int = 0
    role: str
    content_text: str | None = None
    content_json: str
    timestamp: datetime
    input_tokens: int | None = None
    output_tokens: int | None = None
    cache_read_tokens: int | None = None
    cache_creation_tokens: int | None = None
    model: str | None = None


class ParsedSession(BaseModel):
    agent_type: str
    external_id: str
    file_path: str
    cwd: str | None = None
    started_at: datetime
    last_message_at: datetime
    messages: list[ParsedMessage]
    total_usage: TokenUsage = TokenUsage()


class SessionSummary(BaseModel):
    id: int
    agent_type: str
    external_id: str
    project_cwd: str
    project_name: str
    started_at: datetime
    last_message_at: datetime
    message_count: int
    total_input_tokens: int
    total_output_tokens: int
    total_cache_read_tokens: int
    total_cache_creation_tokens: int
    summary: str | None = None


class TokenStats(BaseModel):
    date: str
    agent_type: str
    model: str | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_creation_tokens: int = 0
    session_count: int = 0


class SearchResult(BaseModel):
    session_id: int
    message_id: int
    role: str
    content_text: str
    timestamp: datetime
    session_external_id: str
    agent_type: str
