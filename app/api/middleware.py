import time
import uuid

import structlog
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

logger = structlog.get_logger()


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:  # type: ignore[override]
        request_id = str(uuid.uuid4())[:8]
        start = time.perf_counter()

        request.state.request_id = request_id
        log = logger.bind(request_id=request_id, method=request.method, path=request.url.path)
        log.info("request_started")

        response: Response = await call_next(request)

        elapsed_ms = (time.perf_counter() - start) * 1000
        log.info(
            "request_finished",
            status=response.status_code,
            elapsed_ms=round(elapsed_ms, 1),
        )
        response.headers["X-Request-ID"] = request_id
        return response
