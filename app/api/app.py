from __future__ import annotations

import time
from collections.abc import Callable, Mapping

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.api.schemas import APIErrorResponse, HealthResponse
from app.core.observability import install_request_telemetry
from app.domain.contracts import (
    AnswerStatus,
    Failure,
    FailureCode,
    QueryResponse,
    QueryService,
    SearchRequest,
    SearchResponse,
    SearchService,
    SearchStatus,
    TraceMetadata,
)

ReadinessProbe = Callable[[], Mapping[str, bool]]


def _http_status(failure: Failure) -> int:
    return {
        FailureCode.VALIDATION_ERROR: 422,
        FailureCode.RETRIEVAL_UNAVAILABLE: 503,
        FailureCode.PROVIDER_TIMEOUT: 504,
        FailureCode.PROVIDER_UNAVAILABLE: 503,
        FailureCode.PROVIDER_FAILURE: 502,
        FailureCode.MALFORMED_PROVIDER_OUTPUT: 502,
    }[failure.code]


def _request_id(request: Request) -> str:
    return request.state.request_id


def create_app(
    *,
    search_service: SearchService,
    query_service: QueryService,
    readiness_probe: ReadinessProbe | None = None,
) -> FastAPI:
    """Create an API application with injected application services."""

    app = FastAPI(title="Pre-sales Knowledge API", version="1.0.0")
    app.state.search_service = search_service
    app.state.query_service = query_service
    app.state.readiness_probe = readiness_probe or (lambda: {"readiness_probe_configured": False})

    install_request_telemetry(app)

    @app.exception_handler(RequestValidationError)
    async def request_validation_error(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        # Do not echo rejected values: they may contain document text or credentials.
        response = APIErrorResponse(
            request_id=_request_id(request),
            failure=Failure(
                code=FailureCode.VALIDATION_ERROR,
                message="request validation failed",
                details={"issue_count": len(exc.errors())},
            ),
        )
        return JSONResponse(status_code=422, content=response.model_dump(mode="json"))

    @app.get(
        "/v1/health",
        response_model=HealthResponse,
        responses={503: {"model": HealthResponse}},
    )
    def health(request: Request):
        started = time.perf_counter()
        try:
            dependencies = dict(app.state.readiness_probe())
            dependencies = {str(name): value is True for name, value in dependencies.items()}
        except Exception:
            dependencies = {"readiness_probe": False}
        ready = bool(dependencies) and all(dependencies.values())
        response = HealthResponse(
            ready=ready,
            dependencies=dependencies,
            request_id=_request_id(request),
            latency_ms=max(0.0, (time.perf_counter() - started) * 1000),
        )
        return JSONResponse(
            status_code=200 if ready else 503,
            content=response.model_dump(mode="json"),
        )

    @app.post(
        "/v1/search",
        response_model=SearchResponse,
        responses={
            422: {"model": APIErrorResponse},
            502: {"model": SearchResponse},
            503: {"model": SearchResponse},
            504: {"model": SearchResponse},
        },
    )
    def search(payload: SearchRequest, request: Request):
        request_id = _request_id(request)
        request.state.retrieval_settings = {
            "top_k": payload.top_k,
            "filter_keys": sorted(payload.filters.model_fields_set),
        }
        started = time.perf_counter()
        try:
            result = app.state.search_service.search(payload, request_id=request_id)
        except Exception:
            result = SearchResponse(
                status=SearchStatus.FAILED,
                trace=TraceMetadata(request_id=request_id),
                failure=Failure(
                    code=FailureCode.RETRIEVAL_UNAVAILABLE,
                    message="search service is unavailable",
                    retryable=True,
                ),
            )
        latency_ms = max(0.0, (time.perf_counter() - started) * 1000)
        result = result.model_copy(
            update={
                "trace": result.trace.model_copy(
                    update={"request_id": request_id, "latency_ms": latency_ms}
                )
            }
        )
        if result.status == SearchStatus.FAILED and result.failure is not None:
            return JSONResponse(
                status_code=_http_status(result.failure),
                content=result.model_dump(mode="json"),
            )
        return result

    @app.post(
        "/v1/query",
        response_model=QueryResponse,
        responses={
            422: {"model": APIErrorResponse},
            502: {"model": QueryResponse},
            503: {"model": QueryResponse},
            504: {"model": QueryResponse},
        },
    )
    def query(payload: SearchRequest, request: Request):
        request_id = _request_id(request)
        request.state.retrieval_settings = {
            "top_k": payload.top_k,
            "filter_keys": sorted(payload.filters.model_fields_set),
        }
        started = time.perf_counter()
        try:
            result = app.state.query_service.query(payload, request_id=request_id)
        except Exception:
            result = QueryResponse(
                status=AnswerStatus.FAILED,
                request_id=request_id,
                failure=Failure(
                    code=FailureCode.PROVIDER_UNAVAILABLE,
                    message="query service is unavailable",
                    retryable=True,
                ),
            )
        latency_ms = max(0.0, (time.perf_counter() - started) * 1000)
        trace = TraceMetadata(request_id=request_id, latency_ms=latency_ms)
        if result.trace is not None:
            trace = result.trace.model_copy(
                update={"request_id": request_id, "latency_ms": latency_ms}
            )
        result = result.model_copy(update={"request_id": request_id, "trace": trace})
        request.state.usage = result.metrics.model_dump(mode="json", exclude_none=True)
        if result.status == AnswerStatus.FAILED and result.failure is not None:
            return JSONResponse(
                status_code=_http_status(result.failure),
                content=result.model_dump(mode="json"),
            )
        return result

    return app
