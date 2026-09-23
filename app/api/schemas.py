from __future__ import annotations

from typing import Literal

from pydantic import Field

from app.domain.contracts import ContractId, DomainModel, Failure


class APIErrorResponse(DomainModel):
    request_id: ContractId
    failure: Failure


class HealthResponse(DomainModel):
    live: Literal[True] = True
    ready: bool
    dependencies: dict[str, bool] = Field(default_factory=dict)
    request_id: ContractId
    latency_ms: float = Field(ge=0)
