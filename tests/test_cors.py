"""CORS: the desktop webview / dev server are cross-origin to the API, so allowed
origins must receive Access-Control-Allow-Origin or the browser blocks every request."""
from fastapi.testclient import TestClient

from apps.api.main import app


def test_allowed_origin_gets_cors_header():
    with TestClient(app) as client:
        r = client.get("/health", headers={"origin": "http://localhost:1420"})
        assert r.status_code == 200
        assert r.headers.get("access-control-allow-origin") == "http://localhost:1420"


def test_preflight_is_handled():
    with TestClient(app) as client:
        r = client.options(
            "/agent/design",
            headers={
                "origin": "http://localhost:1420",
                "access-control-request-method": "POST",
                "access-control-request-headers": "content-type",
            },
        )
        assert r.status_code == 200
        assert r.headers.get("access-control-allow-origin") == "http://localhost:1420"


def test_unlisted_origin_gets_no_cors_header():
    with TestClient(app) as client:
        r = client.get("/health", headers={"origin": "http://evil.example.com"})
        assert "access-control-allow-origin" not in r.headers
