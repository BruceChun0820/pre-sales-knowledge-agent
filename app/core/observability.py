from __future__ import annotations

import logging
import time
import uuid
from collections.abc import Callable
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.domain.contracts import Failure, FailureCode

logger = logging.getLogger("app.api")


def install_request_telemetry(app: FastAPI) -> None:
    """Attach request IDs, duration headers, and body-free structured request logs."""

    @app.middleware("http")
    async def request_telemetry(request: Request, call_next: Callable[..., Any]):
        request_id = str(uuid.uuid4())
        request.state.request_id = request_id
        request.state.usage = None
        request.state.retrieval_settings = None
        started = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            response = JSONResponse(
                status_code=500,
                content={
                    "request_id": request_id,
                    "failure": Failure(
                        code=FailureCode.PROVIDER_FAILURE,
                        message="internal service error",
                    ).model_dump(mode="json"),
                },
            )
        latency_ms = max(0.0, (time.perf_counter() - started) * 1000)
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Latency-Ms"] = f"{latency_ms:.3f}"
        usage = request.state.usage or {}
        settings = request.state.retrieval_settings or {}
        logger.info(
            "api_request_completed",
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "latency_ms": round(latency_ms, 3),
                "input_tokens": usage.get("input_tokens"),
                "output_tokens": usage.get("output_tokens"),
                "total_tokens": usage.get("total_tokens"),
                "retrieval_top_k": settings.get("top_k"),
                "retrieval_filter_keys": settings.get("filter_keys"),
            },
        )
        return response
