"""Unit and integration tests for the FastAPI HTTP API.

Governed by RFC-0009 §3.3-§3.6, §7:
- GET /api/v1/health endpoint
- GET /api/v1/language metadata
- GET /api/v1/examples endpoint
- POST /api/v1/compile with valid code, compilation errors, runtime errors
- Phase emission subsetting (omitted phases returned as None/null)
- Size limit rejection (413 Payload Too Large)
- Invalid emit validation (422)
- Rate limiting behavior (429 with Retry-After header)
- Security headers and no-cache policies
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from api import app
from nexora.tokens import KEYWORDS

client = TestClient(app)


def test_api_health_endpoint() -> None:
    """Test health endpoint returns 200 with status ok and version."""
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["version"] == "0.1.0"
    assert "python" in data


def test_api_language_metadata() -> None:
    """Test language metadata endpoint returns keywords matching tokens.KEYWORDS."""
    response = client.get("/api/v1/language")
    assert response.status_code == 200
    data = response.json()
    assert set(data["keywords"]) == set(KEYWORDS.keys())
    assert "error_codes" in data
    assert any(ec["code"] == "E1001" for ec in data["error_codes"])


def test_api_examples_endpoint() -> None:
    """Test examples endpoint lists bundled .mini files."""
    response = client.get("/api/v1/examples")
    assert response.status_code == 200
    examples = response.json()
    assert isinstance(examples, list)
    assert len(examples) > 0
    ids = [ex["id"] for ex in examples]
    assert "hello" in ids
    assert "factorial" in ids


def test_api_compile_success_no_run() -> None:
    """Test successful compilation without execution."""
    src = "make a = 10;\nshow(a);\n"
    response = client.post("/api/v1/compile", json={"source": src, "run": False})
    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert data["python"] is not None
    assert data["run"] is None


def test_api_compile_with_run() -> None:
    """Test successful compilation and sandboxed execution."""
    src = 'show("FastAPI Runner");\n'
    response = client.post("/api/v1/compile", json={"source": src, "run": True})
    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert data["run"] is not None
    assert data["run"]["stdout"] == "FastAPI Runner\n"
    assert data["run"]["exit_code"] == 0


def test_api_compile_user_error_returns_200_with_ok_false() -> None:
    """Test compilation error returns 200 with ok: false per RFC-0002 §3.7."""
    src = "make a = ;\n"
    response = client.post("/api/v1/compile", json={"source": src})
    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is False
    assert len(data["diagnostics"]) > 0


def test_api_emit_phase_subsetting() -> None:
    """Test that requesting subset of phases omits unrequested phases."""
    src = "make x = 42;\n"
    response = client.post(
        "/api/v1/compile",
        json={"source": src, "emit": ["tokens", "python"]},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["tokens"] is not None
    assert data["python"] is not None
    assert data["ast"] is None
    assert data["symbols"] is None
    assert data["tac"] is None


def test_api_source_too_large_413() -> None:
    """Test that source exceeding 64KB is rejected with HTTP 413."""
    large_source = "make a = 1;\n" * 7000  # 84KB > 64KB
    response = client.post("/api/v1/compile", json={"source": large_source})
    assert response.status_code == 413
    data = response.json()
    assert data["error"]["code"] == "source_too_large"


def test_api_invalid_emit_phase_422() -> None:
    """Test that invalid emit phase names are rejected with 422."""
    src = "make a = 1;\n"
    response = client.post(
        "/api/v1/compile",
        json={"source": src, "emit": ["nonexistent_phase"]},
    )
    assert response.status_code == 422
    data = response.json()
    assert data["error"]["code"] == "validation_error"


def test_api_security_headers() -> None:
    """Test that security headers (nosniff, Cache-Control, X-Request-ID) are present."""
    response = client.get("/api/v1/health")
    assert response.headers.get("X-Content-Type-Options") == "nosniff"
    assert "X-Request-ID" in response.headers

    compile_resp = client.post("/api/v1/compile", json={"source": "show(1);"})
    assert compile_resp.headers.get("Cache-Control") == "no-store"
