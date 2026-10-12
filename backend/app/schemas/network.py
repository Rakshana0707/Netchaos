from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, Field, StringConstraints


Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]


class ErrorBody(BaseModel):
    code: str = Field(examples=["node_not_found"])
    message: str
    details: list[dict] | None = None


class ErrorResponse(BaseModel):
    error: ErrorBody


class NetworkCreate(BaseModel):
    name: Name = Field(description="Human-readable network name", examples=["Campus Network"])


class NetworkResponse(BaseModel):
    network_id: str = Field(examples=["net_001"])
    name: str
    created_at: datetime

