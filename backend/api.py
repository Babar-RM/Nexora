"""Nexora FastAPI HTTP Application.

Governed by RFC-0009 §3.3-§3.6.
Exposes:
- GET  /api/v1/health   : Service health and version info
- POST /api/v1/compile  : Compile MiniLang source and optionally run
- GET  /api/v1/examples : List bundled sample programs
- GET  /api/v1/language : Language metadata for frontend editor

Features:
- Security headers (nosniff, no-store for /compile)
- Sliding-window in-memory rate limiting per client IP
- Concurrency limiter semaphore for run execution (NEXORA_MAX_CONCURRENT_RUNS)
- Strict request size limit (NEXORA_MAX_SOURCE_BYTES = 64KB)
- Whitelisted CORS origins
"""

from __future__ import annotations

import asyncio
import os
import pathlib
import sys
import time
from collections import defaultdict, deque
from typing import Any

from fastapi import FastAPI, HTTPException, Request, Response, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from nexora.errors import InternalCompilerError
from nexora.pipeline import ALL_PHASES, CompileOptions, compile_source
from nexora.tokens import KEYWORDS

# =============================================================================
# Configuration & Constants (RFC-0009 §3.4)
# =============================================================================

API_VERSION = "0.1.0"
MAX_SOURCE_BYTES: int = int(os.environ.get("NEXORA_MAX_SOURCE_BYTES", str(64 * 1024)))
DEFAULT_RUN_TIMEOUT: float = float(os.environ.get("NEXORA_RUN_TIMEOUT", "5.0"))
MAX_CONCURRENT_RUNS: int = int(os.environ.get("NEXORA_MAX_CONCURRENT_RUNS", "4"))
RATE_COMPILE_PER_MIN: int = int(os.environ.get("NEXORA_RATE_COMPILE", "60"))
RATE_RUN_PER_MIN: int = int(os.environ.get("NEXORA_RATE_RUN", "12"))
RUN_ENABLED: bool = os.environ.get("NEXORA_RUN_ENABLED", "true").lower() in (
    "true",
    "1",
    "yes",
)
TRUST_PROXY: bool = os.environ.get("NEXORA_TRUST_PROXY", "false").lower() in (
    "true",
    "1",
    "yes",
)
CORS_ORIGINS: list[str] = [
    origin.strip()
    for origin in os.environ.get("NEXORA_CORS_ORIGINS", "http://localhost:5173").split(
        ","
    )
    if origin.strip()
]

# Diagnostics Error Code Table from RFC-0004
ERROR_CODES: list[dict[str, str]] = [
    {"code": "E0000", "phase": "internal", "description": "Too many errors"},
    {"code": "E1001", "phase": "lexer", "description": "Unrecognized character"},
    {"code": "E1002", "phase": "lexer", "description": "Unterminated string literal"},
    {"code": "E1003", "phase": "lexer", "description": "Malformed number literal"},
    {"code": "E1004", "phase": "lexer", "description": "Non-ASCII character"},
    {"code": "E2001", "phase": "parser", "description": "Syntax error"},
    {"code": "E2002", "phase": "parser", "description": "Unexpected token"},
    {"code": "E2003", "phase": "parser", "description": "Missing semicolon"},
    {"code": "E2004", "phase": "parser", "description": "Unclosed delimiter"},
    {"code": "E2005", "phase": "parser", "description": "Missing block"},
    {"code": "E2006", "phase": "parser", "description": "Invalid assignment target"},
    {"code": "E2007", "phase": "parser", "description": "Reserved word as identifier"},
    {"code": "E3001", "phase": "semantic", "description": "Undeclared identifier"},
    {"code": "E3002", "phase": "semantic", "description": "Duplicate declaration"},
    {"code": "E3003", "phase": "semantic", "description": "Type mismatch"},
    {"code": "E3004", "phase": "semantic", "description": "Invalid condition type"},
    {"code": "E3005", "phase": "semantic", "description": "Argument count mismatch"},
    {"code": "E3006", "phase": "semantic", "description": "Argument type mismatch"},
    {"code": "E3007", "phase": "semantic", "description": "Return type mismatch"},
    {"code": "E3008", "phase": "semantic", "description": "Missing return"},
    {"code": "E3009", "phase": "semantic", "description": "Return outside task"},
    {"code": "E3010", "phase": "semantic", "description": "Loop control outside loop"},
    {"code": "E3011", "phase": "semantic", "description": "Nested task declaration"},
    {"code": "E3012", "phase": "semantic", "description": "Shadowing not permitted"},
    {"code": "R5001", "phase": "runner", "description": "Division or modulo by zero"},
    {"code": "R5002", "phase": "runner", "description": "Time limit exceeded"},
    {"code": "R5003", "phase": "runner", "description": "Recursion depth exceeded"},
    {"code": "R5004", "phase": "runner", "description": "Output limit exceeded"},
    {"code": "R5005", "phase": "runner", "description": "Runtime execution failure"},
    {"code": "R5006", "phase": "runner", "description": "Uninitialized variable"},
]


# =============================================================================
# In-Process Sliding Window Rate Limiter (RFC-0009 §3.4)
# =============================================================================


class SlidingWindowRateLimiter:
    """Sliding-window in-memory rate limiter per client key."""

    def __init__(self) -> None:
        self._compile_windows: dict[str, deque[float]] = defaultdict(deque)
        self._run_windows: dict[str, deque[float]] = defaultdict(deque)

    def check_limit(self, client_id: str, is_run: bool) -> tuple[bool, int]:
        """Check whether the client exceeds rate limits.

        Returns (allowed, retry_after_seconds).
        """
        now = time.time()
        window = 60.0

        if is_run:
            times = self._run_windows[client_id]
            limit = RATE_RUN_PER_MIN
        else:
            times = self._compile_windows[client_id]
            limit = RATE_COMPILE_PER_MIN

        # Purge timestamps older than window
        while times and times[0] <= now - window:
            times.popleft()

        if len(times) >= limit:
            oldest = times[0]
            retry_after = max(1, int(window - (now - oldest)))
            return False, retry_after

        times.append(now)
        return True, 0


limiter = SlidingWindowRateLimiter()
run_semaphore = asyncio.Semaphore(MAX_CONCURRENT_RUNS)


# =============================================================================
# Pydantic Request / Response Models (RFC-0009 §3.3)
# =============================================================================


class CompileRequest(BaseModel):
    """Schema for POST /api/v1/compile request body."""

    source: str = Field(..., min_length=1, description="MiniLang source code")
    run: bool = Field(False, description="Execute program in sandbox if true")
    optimize: bool = Field(True, description="Enable compiler optimizations")
    emit: list[str] | None = Field(
        None, description="Subset of compiler phases to emit"
    )


# =============================================================================
# FastAPI App Initialization & Middleware
# =============================================================================

app = FastAPI(
    title="Nexora Compiler API",
    version=API_VERSION,
    description="HTTP API for compiling MiniLang source code into Python and executing safely.",
)

# CORS configuration (RFC-0009 §3.4)
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "X-Request-ID"],
)


@app.middleware("http")
async def security_and_logging_middleware(request: Request, call_next):
    """Enforce security headers and request ID tracking (RFC-0009 §3.4, §3.6)."""
    # Accept X-Request-ID if matches pattern, or generate
    client_req_id = request.headers.get("X-Request-ID")
    import re
    import uuid

    if client_req_id and re.fullmatch(r"[A-Za-z0-9-]{8,64}", client_req_id):
        request_id = client_req_id
    else:
        request_id = str(uuid.uuid4())

    response: Response = await call_next(request)

    # Standard security headers
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Request-ID"] = request_id

    # /compile responses must not be cached by browser
    if request.url.path.endswith("/compile"):
        response.headers["Cache-Control"] = "no-store"

    return response


# =============================================================================
# Custom Exception Handlers (RFC-0009 §3.3)
# =============================================================================


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "error": {
                "code": "validation_error",
                "message": "Invalid request parameters: " + str(exc),
            }
        },
    )


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    # If detail is already formatted dict, use it
    if isinstance(exc.detail, dict) and "code" in exc.detail:
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": exc.detail},
            headers=exc.headers,
        )
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {"code": "bad_request", "message": str(exc.detail)}},
        headers=exc.headers,
    )


@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    # Internal error without leaking traces (RFC-0009 §3.3)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": {
                "code": "internal_error",
                "message": "An unexpected compiler error occurred. Please contact the administrator.",
            }
        },
    )


# =============================================================================
# Helpers
# =============================================================================


def _get_client_ip(request: Request) -> str:
    """Extract client IP address, honoring proxy only if TRUST_PROXY is True."""
    if TRUST_PROXY:
        x_forwarded = request.headers.get("X-Forwarded-For")
        if x_forwarded:
            return x_forwarded.split(",")[0].strip()
    client = request.client
    return client.host if client else "127.0.0.1"


# =============================================================================
# API Endpoints (RFC-0009 §3.3)
# =============================================================================


@app.get("/api/v1/health")
async def health_check() -> dict[str, str]:
    """Liveness probe reporting version and Python runtime."""
    py_ver = (
        f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    )
    return {
        "status": "ok",
        "version": API_VERSION,
        "python": py_ver,
    }


@app.get("/api/v1/language")
async def get_language_metadata() -> dict[str, Any]:
    """Provide MiniLang language specification metadata for editor integration."""
    return {
        "keywords": sorted(KEYWORDS.keys()),
        "types": ["int", "float", "string", "bool", "empty", "void"],
        "operators": [
            "either",
            "both",
            "not",
            "==",
            "!=",
            "<",
            "<=",
            ">",
            ">=",
            "+",
            "-",
            "*",
            "/",
            "%",
            "=",
        ],
        "punctuation": [";", "(", ")", "{", "}", ",", ":"],
        "comment_prefix": "//",
        "error_codes": ERROR_CODES,
    }


@app.get("/api/v1/examples")
async def list_examples() -> list[dict[str, str]]:
    """List bundled MiniLang sample programs from backend/examples/."""
    examples_dir = pathlib.Path(__file__).parent / "examples"
    results: list[dict[str, str]] = []
    if examples_dir.exists() and examples_dir.is_dir():
        for file in sorted(examples_dir.glob("*.mini")):
            name = file.stem
            title = name.replace("_", " ").title()
            try:
                content = file.read_text(encoding="utf-8")
                results.append({"id": name, "title": title, "source": content})
            except OSError:
                continue
    return results


@app.post("/api/v1/compile")
async def compile_endpoint(req: CompileRequest, request: Request) -> dict[str, Any]:
    """Compile and optionally run MiniLang source code."""
    # 1. Source size validation (RFC-0009 §3.3, §3.4)
    source_bytes = len(req.source.encode("utf-8"))
    if source_bytes > MAX_SOURCE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail={
                "code": "source_too_large",
                "message": f"Source size ({source_bytes} bytes) exceeds limit of {MAX_SOURCE_BYTES} bytes",
            },
        )

    # 2. Emit phase validation
    if req.emit is not None:
        invalid_phases = [p for p in req.emit if p not in ALL_PHASES]
        if invalid_phases:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={
                    "code": "validation_error",
                    "message": f"Invalid emit phase(s): {', '.join(invalid_phases)}",
                },
            )

    # 3. Rate limiting check
    client_ip = _get_client_ip(request)
    allowed, retry_after = limiter.check_limit(client_ip, is_run=req.run)
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "code": "rate_limited",
                "message": "Rate limit exceeded. Please try again later.",
            },
            headers={"Retry-After": str(retry_after)},
        )

    # 4. Concurrency management for execution
    should_run = req.run and RUN_ENABLED
    if should_run:
        try:
            # Wait at most 2.0s for slot per RFC-0009 §3.1.5
            await asyncio.wait_for(run_semaphore.acquire(), timeout=2.0)
        except TimeoutError:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={
                    "code": "busy",
                    "message": "Runner pool is currently at maximum capacity. Please retry shortly.",
                },
            )
        try:
            compile_opts = CompileOptions(
                run=True,
                optimize=req.optimize,
                emit=req.emit,
                timeout_seconds=DEFAULT_RUN_TIMEOUT,
            )
            # Run in worker thread to prevent blocking asyncio event loop
            loop = asyncio.get_running_loop()
            result = await loop.run_in_executor(
                None, compile_source, req.source, compile_opts
            )
        except InternalCompilerError as ice:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail={"code": "internal_error", "message": str(ice)},
            )
        finally:
            run_semaphore.release()
    else:
        # Compilation only (or run disabled)
        compile_opts = CompileOptions(
            run=False,
            optimize=req.optimize,
            emit=req.emit,
        )
        loop = asyncio.get_running_loop()
        try:
            result = await loop.run_in_executor(
                None, compile_source, req.source, compile_opts
            )
        except InternalCompilerError as ice:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail={"code": "internal_error", "message": str(ice)},
            )

    return result.to_dict()
